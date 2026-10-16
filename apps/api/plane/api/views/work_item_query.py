# BlockWill fork — work item querying for the v1 API: `pql` and `filters` on
# list endpoints, plus the workspace-wide list and count endpoints that Plane
# Cloud has and Community Edition lacks. This is what the Plane MCP server's
# `workitem list` / `workitem count` call.
#
#   GET /api/v1/workspaces/<slug>/work-items/?pql=...
#   GET /api/v1/workspaces/<slug>/work-items/count/?pql=...&group_by=...&sub_group_by=...
#   GET /api/v1/workspaces/<slug>/projects/<id>/archived-work-items/?pql=...

from collections import defaultdict

from django.db.models import F, Func, OuterRef, Q
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from plane.api.serializers import IssueSerializer
from plane.app.permissions import ProjectEntityPermission, WorkspaceEntityPermission
from plane.db.models import (
    CycleIssue,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueMilestone,
    ModuleIssue,
    ProjectMember,
)
from plane.db.models.project import ROLE
from plane.utils.filters import ComplexFilterBackend, IssueFilterSet
from plane.utils.order_queryset import order_issue_queryset
from plane.utils.pql import PQLError, compile_pql, work_item_base_queryset

from .base import BaseAPIView


class _FilterView:
    """What ComplexFilterBackend reads off a view."""

    filterset_class = IssueFilterSet


class WorkItemQueryError(Exception):
    def __init__(self, body):
        super().__init__(str(body))
        self.body = body

    def response(self):
        return Response(self.body, status=status.HTTP_400_BAD_REQUEST)


def work_item_query(request, slug, project_id=None):
    """The `pql` and `filters` query parameters as (Q or None, hidden kinds).

    Raises WorkItemQueryError with a 400 body naming the problem; the MCP
    server turns a body with a `pql` key into a correctable answer.
    """
    q = None
    hidden = set()

    pql = (request.GET.get("pql") or "").strip()
    if pql:
        try:
            q, hidden = compile_pql(pql, slug, request.user, project_id)
        except PQLError as exc:
            raise WorkItemQueryError({"pql": str(exc)}) from exc

    raw_filters = request.GET.get("filters")
    if raw_filters:
        try:
            matched = ComplexFilterBackend().filter_queryset(
                request, Issue.objects.filter(workspace__slug=slug), _FilterView(), filter_data=raw_filters
            )
        except DRFValidationError as exc:
            raise WorkItemQueryError({"filters": exc.detail}) from exc
        filters_q = Q(id__in=matched.values("id"))
        q = filters_q if q is None else q & filters_q

    return q, hidden


def visible_to(user, slug):
    """Work items the user can see across the workspace: projects they are an
    active member of, and only their own items where they are a guest without
    full feature access."""
    memberships = ProjectMember.objects.filter(
        workspace__slug=slug, member=user, is_active=True, project__archived_at__isnull=True
    ).values_list("project_id", "role", "project__guest_view_all_features")
    full, own_only = [], []
    for project_id, role, guest_view_all in memberships:
        (own_only if role == ROLE.GUEST.value and not guest_view_all else full).append(project_id)
    return Q(project_id__in=full) | Q(project_id__in=own_only, created_by=user)


def _with_list_annotations(queryset):
    return (
        queryset.annotate(
            sub_issues_count=Issue.issue_objects.filter(parent=OuterRef("id"))
            .order_by()
            .annotate(count=Func(F("id"), function="Count"))
            .values("count")
        )
        .select_related("project", "workspace", "state", "parent")
        .prefetch_related("assignees", "labels")
    )


class WorkspaceWorkItemListAPIEndpoint(BaseAPIView):
    """Work items across every project the caller can see."""

    permission_classes = [WorkspaceEntityPermission]
    use_read_replica = True

    def get(self, request, slug):
        try:
            q, hidden = work_item_query(request, slug)
        except WorkItemQueryError as exc:
            return exc.response()

        base = work_item_base_queryset(hidden).filter(workspace__slug=slug).filter(visible_to(request.user, slug))
        if q is not None:
            base = base.filter(q)
        base = base.distinct()

        order_by = request.GET.get("order_by", "-created_at")
        issues, _ = order_issue_queryset(issue_queryset=_with_list_annotations(base), order_by_param=order_by)

        return self.paginate(
            request=request,
            queryset=issues,
            total_count_queryset=base,
            on_results=lambda rows: IssueSerializer(rows, many=True, fields=self.fields, expand=self.expand).data,
        )


class ArchivedWorkItemListAPIEndpoint(BaseAPIView):
    """Archived work items in one project (what `workitem list_archived` calls)."""

    permission_classes = [ProjectEntityPermission]
    use_read_replica = True

    def get(self, request, slug, project_id):
        try:
            q, hidden = work_item_query(request, slug, project_id)
        except WorkItemQueryError as exc:
            return exc.response()

        base = work_item_base_queryset(hidden | {"archived"}).filter(
            workspace__slug=slug, project_id=project_id, archived_at__isnull=False
        )
        if ProjectMember.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            member=request.user,
            role=ROLE.GUEST.value,
            is_active=True,
            project__guest_view_all_features=False,
        ).exists():
            base = base.filter(created_by=request.user)
        if q is not None:
            base = base.filter(q)
        base = base.distinct()

        issues, _ = order_issue_queryset(
            issue_queryset=_with_list_annotations(base), order_by_param=request.GET.get("order_by", "-archived_at")
        )
        return self.paginate(
            request=request,
            queryset=issues,
            total_count_queryset=base,
            on_results=lambda rows: IssueSerializer(rows, many=True, fields=self.fields, expand=self.expand).data,
        )


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------


def _join_values(model, column):
    """issue_id -> keys, for a many-valued dimension stored in a join table."""

    def values(issue_ids):
        mapping = defaultdict(set)
        rows = model.objects.filter(issue_id__in=issue_ids, deleted_at__isnull=True).values_list("issue_id", column)
        for issue_id, key in rows:
            mapping[issue_id].add(str(key))
        return mapping

    return values


def _column_values(column):
    def values(issue_ids):
        rows = Issue.objects.filter(id__in=issue_ids).values_list("id", column)
        return {issue_id: {"None" if key is None else str(key)} for issue_id, key in rows}

    return values


GROUP_DIMENSIONS = {
    "state_id": _column_values("state_id"),
    "state__group": _column_values("state__group"),
    "priority": _column_values("priority"),
    "project_id": _column_values("project_id"),
    "type_id": _column_values("type_id"),
    "created_by": _column_values("created_by_id"),
    "target_date": _column_values("target_date"),
    "start_date": _column_values("start_date"),
    "labels__id": _join_values(IssueLabel, "label_id"),
    "assignees__id": _join_values(IssueAssignee, "assignee_id"),
    "issue_module__module_id": _join_values(ModuleIssue, "module_id"),
    "cycle_id": _join_values(CycleIssue, "cycle_id"),
    "milestone_id": _join_values(IssueMilestone, "milestone_id"),
}

UNSUPPORTED_DIMENSIONS = {
    "release_work_items__release_id": "Releases are not available on this Plane edition.",
}


class WorkspaceWorkItemCountAPIEndpoint(BaseAPIView):
    """Count work items, optionally grouped by one or two dimensions.

    Response matches Plane Cloud's WorkItemGroupedCountResponse:
    {grouped_by, sub_grouped_by, total_count, grouped_counts: {key: {count,
    sub_grouped_counts?: {key: {count}}}}}. A work item with several values
    in a many-valued dimension (labels, assignees, ...) counts once in each of
    its groups; one with none counts under "None". total_count counts each
    work item once.
    """

    permission_classes = [WorkspaceEntityPermission]
    use_read_replica = True

    def get(self, request, slug):
        group_by = request.GET.get("group_by") or None
        sub_group_by = request.GET.get("sub_group_by") or None
        for name, value in (("group_by", group_by), ("sub_group_by", sub_group_by)):
            if value in UNSUPPORTED_DIMENSIONS:
                return Response({"error": UNSUPPORTED_DIMENSIONS[value]}, status=status.HTTP_400_BAD_REQUEST)
            if value is not None and value not in GROUP_DIMENSIONS:
                return Response(
                    {"error": f"{name} must be one of: {', '.join(GROUP_DIMENSIONS)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if sub_group_by and not group_by:
            return Response({"error": "sub_group_by needs group_by"}, status=status.HTTP_400_BAD_REQUEST)
        if sub_group_by and sub_group_by == group_by:
            return Response({"error": "group_by and sub_group_by must differ"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            q, hidden = work_item_query(request, slug)
        except WorkItemQueryError as exc:
            return exc.response()

        base = work_item_base_queryset(hidden).filter(workspace__slug=slug).filter(visible_to(request.user, slug))
        if q is not None:
            base = base.filter(q)
        issue_ids = list(base.order_by().values_list("id", flat=True).distinct())

        body = {
            "grouped_by": group_by,
            "sub_grouped_by": sub_group_by,
            "total_count": len(issue_ids),
            "grouped_counts": {},
        }
        if not group_by or not issue_ids:
            return Response(body)

        groups = GROUP_DIMENSIONS[group_by](issue_ids)
        sub_groups = GROUP_DIMENSIONS[sub_group_by](issue_ids) if sub_group_by else None

        counts = {}
        for issue_id in issue_ids:
            for key in groups.get(issue_id) or {"None"}:
                entry = counts.setdefault(key, {"count": 0})
                entry["count"] += 1
                if sub_groups is not None:
                    nested = entry.setdefault("sub_grouped_counts", {})
                    for sub_key in sub_groups.get(issue_id) or {"None"}:
                        nested.setdefault(sub_key, {"count": 0})["count"] += 1

        body["grouped_counts"] = dict(sorted(counts.items(), key=lambda kv: -kv[1]["count"]))
        return Response(body)
