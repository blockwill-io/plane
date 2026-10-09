# BlockWill fork — v1 (public API) agent assignment endpoints. This is what the
# Plane MCP server calls, which is how StartupOS finds its queue.
#
#   GET  /api/v1/workspaces/<slug>/agent-assignments/?agent=startupos
#        -> every work item in the workspace handed to the agent, with enough
#           of the work item inline (identifier, name, state, assignees) that
#           the agent can triage without a retrieve per row.
#   GET/POST/DELETE /api/v1/workspaces/<slug>/projects/<id>/work-items/<pk>/agent-assignment/
#        -> one work item's hand-off; POST assigns, DELETE takes it back.

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ProjectEntityPermission, WorkspaceEntityPermission
from plane.db.models import AGENTS, Issue, IssueAgentAssignment
from plane.utils.agent_assignment import assign_agent, get_assignment, serialize_assignment, unassign_agent

from .base import BaseAPIView

DEFAULT_AGENT = "startupos"


def _agent_from(request):
    agent = request.data.get("agent") or request.query_params.get("agent") or DEFAULT_AGENT
    return agent if agent in AGENTS else None


def _work_item_summary(issue: Issue) -> dict:
    state = issue.state
    return {
        "id": str(issue.id),
        "identifier": f"{issue.project.identifier}-{issue.sequence_id}",
        "sequence_id": issue.sequence_id,
        "name": issue.name,
        "project_id": str(issue.project_id),
        "project_identifier": issue.project.identifier,
        "state_id": str(issue.state_id) if issue.state_id else None,
        "state_name": state.name if state else None,
        "state_group": state.group if state else None,
        "priority": issue.priority,
        "assignee_ids": [str(user.id) for user in issue.assignees.all()],
        "target_date": issue.target_date,
        "archived_at": issue.archived_at,
        "updated_at": issue.updated_at,
    }


class WorkspaceAgentAssignmentListAPIEndpoint(BaseAPIView):
    """The agent's queue across the whole workspace."""

    permission_classes = [WorkspaceEntityPermission]

    def get(self, request, slug):
        agent = _agent_from(request)
        if agent is None:
            return Response(
                {"error": f"unknown agent; known agents: {', '.join(AGENTS)}"}, status=status.HTTP_400_BAD_REQUEST
            )
        assignments = (
            IssueAgentAssignment.objects.filter(workspace__slug=slug, agent=agent)
            .select_related("assigned_by", "issue", "issue__project", "issue__state")
            .prefetch_related("issue__assignees")
            .order_by("created_at")
        )
        results = []
        for assignment in assignments:
            issue = assignment.issue
            if issue.deleted_at is not None:
                continue
            results.append({**serialize_assignment(assignment), "work_item": _work_item_summary(issue)})
        return Response({"agent": agent, "count": len(results), "results": results})


class WorkItemAgentAssignmentAPIEndpoint(BaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def _issue(self, slug, project_id, pk):
        return (
            Issue.objects.filter(workspace__slug=slug, project_id=project_id, pk=pk)
            .select_related("project", "state")
            .first()
        )

    def get(self, request, slug, project_id, pk):
        agent = _agent_from(request)
        if agent is None:
            return Response({"error": "unknown agent"}, status=status.HTTP_400_BAD_REQUEST)
        assignment = get_assignment(pk, agent)
        return Response(
            {
                "agent": agent,
                "assigned": assignment is not None,
                "assignment": serialize_assignment(assignment) if assignment else None,
            }
        )

    def post(self, request, slug, project_id, pk):
        issue = self._issue(slug, project_id, pk)
        if issue is None:
            return Response({"error": "Work item not found"}, status=status.HTTP_404_NOT_FOUND)
        agent = _agent_from(request)
        if agent is None:
            return Response({"error": "unknown agent"}, status=status.HTTP_400_BAD_REQUEST)
        assignment, created = assign_agent(issue, agent, request.user)
        return Response(
            {**serialize_assignment(assignment), "work_item": _work_item_summary(issue)},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, slug, project_id, pk):
        issue = self._issue(slug, project_id, pk)
        if issue is None:
            return Response({"error": "Work item not found"}, status=status.HTTP_404_NOT_FOUND)
        agent = _agent_from(request)
        if agent is None:
            return Response({"error": "unknown agent"}, status=status.HTTP_400_BAD_REQUEST)
        removed = unassign_agent(issue, agent, request.user)
        return Response({"agent": agent, "removed": removed}, status=status.HTTP_200_OK)
