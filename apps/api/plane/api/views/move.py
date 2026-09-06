# BlockWill fork addition — move a work item (and its sub-items) between
# projects in the same workspace. Upstream Plane has no such operation: every
# issue endpoint is project-scoped and state/labels/sequence are per-project.
#
# Kept in its own file so upstream merges never conflict.

# Python imports
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ProjectEntityPermission, ROLE
from plane.db.models import (
    CommentReaction,
    CycleIssue,
    FileAsset,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueComment,
    IssueDescriptionVersion,
    IssueLabel,
    IssueLink,
    IssueMention,
    IssueReaction,
    IssueRelation,
    IssueSequence,
    IssueSubscriber,
    IssueVersion,
    IssueVote,
    Label,
    ModuleIssue,
    Project,
    ProjectMember,
    State,
)
from plane.utils.uuid import convert_uuid_to_integer
from .base import BaseAPIView

# Related rows that only need their denormalized project pointer rewritten.
PROJECT_SCOPED_RELATED = (
    IssueLink,
    IssueComment,
    CommentReaction,
    IssueReaction,
    IssueSubscriber,
    IssueMention,
    IssueActivity,
    IssueVersion,
    IssueDescriptionVersion,
    IssueVote,
)

MAX_SUB_ITEM_DEPTH = 10


class MoveWorkItemAPIEndpoint(BaseAPIView):
    """Move a work item to another project in the same workspace.

    POST body: {"target_project_id": "<uuid>"}

    Sub-items move along with the parent. Project-scoped associations are
    remapped: state by name (falling back to the target's default state),
    labels by name (created in the target if missing), assignees kept only
    when they are members of the target project. Cycle/module links and the
    estimate point are dropped. A fresh sequence number is issued, so the
    work item gets a new identifier.
    """

    model = Issue
    permission_classes = [ProjectEntityPermission]

    def _resolve_state(self, source_state, target_project):
        if source_state is not None:
            match = State.objects.filter(project=target_project, name__iexact=source_state.name).first()
            if match:
                return match
            group_match = (
                State.objects.filter(project=target_project, group=source_state.group).order_by("sequence").first()
            )
            if group_match:
                return group_match
        return (
            State.objects.filter(project=target_project, default=True).first()
            or State.objects.filter(project=target_project).order_by("sequence").first()
        )

    def _next_sequence_id(self, target_project):
        # Same advisory-lock pattern as Issue.save() so we never race a
        # concurrent create in the target project.
        lock_key = convert_uuid_to_integer(target_project.id)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
        last_sequence = IssueSequence.objects.filter(project=target_project).aggregate(largest=Max("sequence"))[
            "largest"
        ]
        return (last_sequence or 0) + 1

    def _move_one(self, issue, source_project, target_project, actor):
        new_state = self._resolve_state(issue.state, target_project)

        # Labels: remap by name, creating missing ones so no information is lost.
        for issue_label in IssueLabel.objects.filter(issue=issue).select_related("label"):
            target_label = Label.objects.filter(project=target_project, name__iexact=issue_label.label.name).first()
            if target_label is None:
                target_label = Label.objects.create(
                    project=target_project,
                    workspace=issue.workspace,
                    name=issue_label.label.name,
                    color=issue_label.label.color,
                    created_by_id=actor.id,
                )
            issue_label.label = target_label
            issue_label.project = target_project
            issue_label.save(update_fields=["label", "project"])

        # Assignees: keep only target-project members.
        for issue_assignee in IssueAssignee.objects.filter(issue=issue):
            is_member = ProjectMember.objects.filter(
                project=target_project, member_id=issue_assignee.assignee_id, is_active=True
            ).exists()
            if is_member:
                issue_assignee.project = target_project
                issue_assignee.save(update_fields=["project"])
            else:
                issue_assignee.delete()

        # Cycle and module membership is meaningless across projects.
        CycleIssue.objects.filter(issue=issue).delete()
        ModuleIssue.objects.filter(issue=issue).delete()

        # Relations where this issue is the subject follow it; rows where it
        # is the object stay in the other issue's project context.
        IssueRelation.objects.filter(issue=issue).update(project=target_project)

        for related_model in PROJECT_SCOPED_RELATED:
            related_model.objects.filter(issue=issue).update(project=target_project)
        FileAsset.objects.filter(issue=issue).update(project=target_project)

        sequence_id = self._next_sequence_id(target_project)

        issue.project = target_project
        issue.state = new_state
        issue.estimate_point = None
        issue.sequence_id = sequence_id
        largest_sort_order = Issue.objects.filter(project=target_project, state=new_state).aggregate(
            largest=Max("sort_order")
        )["largest"]
        if largest_sort_order is not None:
            issue.sort_order = largest_sort_order + 10000
        issue.save()

        IssueSequence.objects.create(
            issue=issue, sequence=sequence_id, project=target_project, workspace=issue.workspace
        )

        IssueActivity.objects.create(
            issue=issue,
            project=target_project,
            workspace=issue.workspace,
            actor=actor,
            verb="updated",
            field="project",
            old_value=source_project.name,
            new_value=target_project.name,
            old_identifier=source_project.id,
            new_identifier=target_project.id,
            comment=f"moved the work item from {source_project.name} to {target_project.name}",
            epoch=timezone.now().timestamp(),
        )

    def post(self, request, slug, project_id, pk):
        target_project_id = request.data.get("target_project_id")
        if not target_project_id:
            return Response({"error": "target_project_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if str(target_project_id) == str(project_id):
            return Response(
                {"error": "target project is the same as the source project"}, status=status.HTTP_400_BAD_REQUEST
            )

        issue = Issue.objects.filter(workspace__slug=slug, project_id=project_id, pk=pk).first()
        if issue is None:
            return Response({"error": "work item not found"}, status=status.HTTP_404_NOT_FOUND)
        if issue.archived_at:
            return Response({"error": "archived work items cannot be moved"}, status=status.HTTP_400_BAD_REQUEST)
        if issue.is_draft or (issue.state and issue.state.group == "triage"):
            return Response(
                {"error": "draft and intake work items cannot be moved"}, status=status.HTTP_400_BAD_REQUEST
            )

        target_project = Project.objects.filter(
            pk=target_project_id, workspace__slug=slug, archived_at__isnull=True
        ).first()
        if target_project is None:
            return Response({"error": "target project not found"}, status=status.HTTP_404_NOT_FOUND)

        if not ProjectMember.objects.filter(
            project=target_project,
            member=request.user,
            is_active=True,
            role__gte=ROLE.MEMBER.value,
        ).exists():
            return Response(
                {"error": "you must be a member of the target project"}, status=status.HTTP_403_FORBIDDEN
            )

        source_project = issue.project

        # Collect the issue plus all its descendants, breadth-first.
        to_move = [issue]
        frontier = [issue.id]
        for _ in range(MAX_SUB_ITEM_DEPTH):
            children = list(Issue.objects.filter(parent_id__in=frontier, project_id=project_id))
            if not children:
                break
            to_move.extend(children)
            frontier = [child.id for child in children]

        with transaction.atomic():
            # The root loses its parent link unless the parent already lives
            # in the target project; descendants keep theirs (they move too).
            if issue.parent_id and issue.parent.project_id != target_project.id:
                issue.parent = None

            for item in to_move:
                self._move_one(item, source_project, target_project, request.user)

        return Response(
            {
                "id": str(issue.id),
                "project_id": str(target_project.id),
                "sequence_id": issue.sequence_id,
                "identifier": f"{target_project.identifier}-{issue.sequence_id}",
                "moved_count": len(to_move),
            },
            status=status.HTTP_200_OK,
        )
