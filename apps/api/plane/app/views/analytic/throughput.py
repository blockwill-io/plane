# BlockWill fork — team throughput report.
#
# "How much work did we finish, and who finished it?" over a chosen window.
# Returns the total completed count plus a per-assignee breakdown, each with
# the actual work items so the UI can link straight to them.

from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, Project

# Guard rail: a very wide window on a busy workspace could return a lot of rows.
# Counts stay exact; only the itemised list is capped.
MAX_ITEMS = 2000


class ThroughputAnalyticsEndpoint(BaseAPIView):
    """Completed work over a date window, aggregated and per assignee."""

    def _parse_date(self, value, default):
        if not value:
            return default
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except (TypeError, ValueError):
            return default
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, project_id=None):
        now = timezone.now()
        # Default window: the last 7 days.
        start_date = self._parse_date(request.GET.get("start_date"), now - timedelta(days=7))
        end_raw = request.GET.get("end_date")
        end_date = self._parse_date(end_raw, now)
        if end_raw:
            # An end date is inclusive of that whole day.
            end_date = end_date + timedelta(days=1)

        # Only projects the caller actually belongs to.
        accessible_projects = Project.objects.filter(
            workspace__slug=slug,
            project_projectmember__member=request.user,
            project_projectmember__is_active=True,
            archived_at__isnull=True,
        ).values_list("id", flat=True)

        project_ids = [pid for pid in (request.GET.get("project_ids") or "").split(",") if pid]
        if project_id:
            project_ids = [str(project_id)]

        queryset = (
            Issue.issue_objects.filter(
                workspace__slug=slug,
                project_id__in=accessible_projects,
                state__group="completed",
                completed_at__gte=start_date,
                completed_at__lt=end_date,
            )
            .select_related("project", "state")
            .prefetch_related("assignees")
        )
        if project_ids:
            queryset = queryset.filter(project_id__in=project_ids)

        total_completed = queryset.count()

        # Group by assignee. A work item with several assignees counts for each
        # of them (the question is "who worked on it"), so per-assignee counts
        # can sum to more than the total — the UI labels the total separately.
        buckets = {}

        def bucket_for(key, name, avatar):
            if key not in buckets:
                buckets[key] = {
                    "assignee_id": key,
                    "display_name": name,
                    "avatar_url": avatar,
                    "count": 0,
                    "work_items": [],
                }
            return buckets[key]

        for issue in queryset.order_by("-completed_at")[:MAX_ITEMS]:
            item = {
                "id": str(issue.id),
                "sequence_id": issue.sequence_id,
                "name": issue.name,
                "project_id": str(issue.project_id),
                "project_identifier": issue.project.identifier,
                "identifier": f"{issue.project.identifier}-{issue.sequence_id}",
                "state_name": issue.state.name if issue.state else None,
                "completed_at": issue.completed_at,
            }
            assignees = list(issue.assignees.all())
            if not assignees:
                bucket_for(None, "Unassigned", None)["work_items"].append(item)
                buckets[None]["count"] += 1
                continue
            for member in assignees:
                b = bucket_for(str(member.id), member.display_name, member.avatar_url)
                b["count"] += 1
                b["work_items"].append(item)

        by_assignee = sorted(buckets.values(), key=lambda b: b["count"], reverse=True)

        return Response(
            {
                "start_date": start_date,
                "end_date": end_date,
                "total_completed": total_completed,
                "is_truncated": total_completed > MAX_ITEMS,
                "by_assignee": by_assignee,
            },
            status=status.HTTP_200_OK,
        )
