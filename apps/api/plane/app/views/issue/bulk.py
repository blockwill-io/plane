# BlockWill fork — bulk property updates for work items.
#
# CE ships the whole client half of bulk operations: the multi-select layer,
# IssueService.bulkOperations(), and bulkUpdateProperties() on every issue
# store. What it does not ship is the endpoint they call, so the feature is
# dead behind an "Upgrade to One" banner. This is that endpoint.
#
# The route and payload deliberately match what the existing client already
# sends (TBulkOperationsPayload: {issue_ids, properties}), so no service or
# store code has to change.
#
# Semantics follow the client's optimistic update in bulkUpdateProperties()
# exactly, because the two must agree or the list will show something the
# server did not do:
#   - scalars (state_id, priority, dates, estimate) REPLACE
#   - lists (assignee_ids, label_ids) APPEND, they never remove
#
# Deliberately NOT using Issue.objects.bulk_update() for the state change:
# bulk_update() bypasses Model.save(), and save() is where _sync_completed_at
# lives. Verified against the live database — a state change through save()
# sets completed_at, the same change through bulk_update() leaves it null,
# which would silently drop bulk-completed work items out of the throughput
# report. A selection is bounded by what a person can select, so per-issue
# save() is the right trade.

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import allow_permission, ROLE
from plane.app.serializers import IssueSerializer
from plane.app.views.base import BaseAPIView
from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import (
    EstimatePoint,
    Issue,
    IssueAssignee,
    IssueLabel,
    Label,
    ProjectMember,
    State,
)
from plane.utils.host import base_host

PRIORITIES = {"urgent", "high", "medium", "low", "none"}
# Scalar columns a bulk edit may set directly on the work item.
SCALAR_FIELDS = ("state_id", "priority", "start_date", "target_date", "estimate_point")


class IssueBulkOperationEndpoint(BaseAPIView):
    """Apply one set of property changes across a selection of work items."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id):
        issue_ids = request.data.get("issue_ids", [])
        properties = request.data.get("properties") or {}

        if not issue_ids:
            return Response({"error": "issue_ids are required"}, status=status.HTTP_400_BAD_REQUEST)
        if not properties:
            return Response({"error": "properties are required"}, status=status.HTTP_400_BAD_REQUEST)

        error = self._validate(slug, project_id, properties)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        assignee_ids = [str(i) for i in (properties.get("assignee_ids") or [])]
        label_ids = [str(i) for i in (properties.get("label_ids") or [])]

        issues = list(
            Issue.objects.filter(
                workspace__slug=slug, project_id=project_id, pk__in=issue_ids
            ).prefetch_related("assignees", "labels")
        )
        if not issues:
            return Response({"error": "No matching work items"}, status=status.HTTP_400_BAD_REQUEST)

        epoch = int(timezone.now().timestamp())
        actor_id = str(request.user.id)
        origin = base_host(request=request, is_app=True)
        updated = 0

        for issue in issues:
            # Snapshot before anything changes; the activity differ needs it.
            current_instance = json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder)
            requested_data = {}
            changed_columns = []

            for field in SCALAR_FIELDS:
                if field not in properties:
                    continue
                value = properties[field]
                if getattr(issue, field) == value:
                    continue
                setattr(issue, field, value)
                changed_columns.append(field)
                requested_data[field] = value

            if changed_columns:
                # save(), not bulk_update() — see the module docstring.
                issue.save(update_fields=changed_columns)

            if assignee_ids:
                before = {str(a.id) for a in issue.assignees.all()}
                missing = [i for i in assignee_ids if i not in before]
                if missing:
                    IssueAssignee.objects.bulk_create(
                        [
                            IssueAssignee(
                                issue=issue,
                                assignee_id=member_id,
                                project_id=project_id,
                                workspace_id=issue.workspace_id,
                                created_by_id=request.user.id,
                            )
                            for member_id in missing
                        ],
                        batch_size=10,
                        ignore_conflicts=True,
                    )
                    requested_data["assignee_ids"] = sorted(before | set(missing))

            if label_ids:
                before = {str(item.id) for item in issue.labels.all()}
                missing = [i for i in label_ids if i not in before]
                if missing:
                    IssueLabel.objects.bulk_create(
                        [
                            IssueLabel(
                                issue=issue,
                                label_id=label_id,
                                project_id=project_id,
                                workspace_id=issue.workspace_id,
                                created_by_id=request.user.id,
                            )
                            for label_id in missing
                        ],
                        batch_size=10,
                        ignore_conflicts=True,
                    )
                    requested_data["label_ids"] = sorted(before | set(missing))

            if not requested_data:
                continue

            updated += 1
            issue_activity.delay(
                type="issue.activity.updated",
                requested_data=json.dumps(requested_data, cls=DjangoJSONEncoder),
                actor_id=actor_id,
                issue_id=str(issue.id),
                project_id=str(project_id),
                current_instance=current_instance,
                epoch=epoch,
                notification=True,
                origin=origin,
            )

        return Response({"updated": updated}, status=status.HTTP_200_OK)

    def _validate(self, slug, project_id, properties):
        """Every referenced object must belong to this project.

        Without this an id from another project would be written straight onto
        the work item, which is a cross-project data leak rather than a 400.
        """
        priority = properties.get("priority")
        if priority is not None and priority not in PRIORITIES:
            return "Invalid priority"

        state_id = properties.get("state_id")
        if state_id and not State.objects.filter(
            id=state_id, project_id=project_id, workspace__slug=slug
        ).exists():
            return "Invalid state for this project"

        estimate_point = properties.get("estimate_point")
        if estimate_point and not EstimatePoint.objects.filter(
            id=estimate_point, project_id=project_id, workspace__slug=slug
        ).exists():
            return "Invalid estimate point for this project"

        assignee_ids = properties.get("assignee_ids") or []
        if assignee_ids:
            valid = ProjectMember.objects.filter(
                project_id=project_id,
                workspace__slug=slug,
                member_id__in=assignee_ids,
                is_active=True,
            ).count()
            if valid != len(set(map(str, assignee_ids))):
                return "One or more assignees are not active members of this project"

        label_ids = properties.get("label_ids") or []
        if label_ids:
            valid = Label.objects.filter(
                project_id=project_id, workspace__slug=slug, id__in=label_ids
            ).count()
            if valid != len(set(map(str, label_ids))):
                return "One or more labels do not belong to this project"

        return None
