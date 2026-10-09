# BlockWill fork — agent assignment endpoints for the web app.
# See plane/db/models/agent_assignment.py and plane/utils/agent_assignment.py.

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.db.models import AGENTS, Issue, IssueAgentAssignment
from plane.utils.agent_assignment import assign_agent, get_assignment, serialize_assignment, unassign_agent

from .base import BaseAPIView

DEFAULT_AGENT = "startupos"


class ProjectAgentAssignmentSummaryEndpoint(BaseAPIView):
    """{issue_id: assignment} for a whole project — one request feeds every
    list / kanban / spreadsheet row's badge."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        assignments = IssueAgentAssignment.objects.filter(workspace__slug=slug, project_id=project_id).select_related(
            "assigned_by"
        )
        return Response({str(a.issue_id): serialize_assignment(a) for a in assignments})


class IssueAgentAssignmentEndpoint(BaseAPIView):
    """Read, set and clear one work item's agent assignment."""

    def _issue(self, slug, project_id, issue_id):
        return Issue.objects.filter(workspace__slug=slug, project_id=project_id, pk=issue_id).first()

    def _agent(self, request):
        agent = request.data.get("agent") or request.query_params.get("agent") or DEFAULT_AGENT
        return agent if agent in AGENTS else None

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        agent = self._agent(request)
        if agent is None:
            return Response({"error": "unknown agent"}, status=status.HTTP_400_BAD_REQUEST)
        assignment = get_assignment(issue_id, agent)
        return Response(
            {
                "agent": agent,
                "assigned": assignment is not None,
                "assignment": serialize_assignment(assignment) if assignment else None,
            }
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id):
        issue = self._issue(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Work item not found"}, status=status.HTTP_404_NOT_FOUND)
        agent = self._agent(request)
        if agent is None:
            return Response({"error": "unknown agent"}, status=status.HTTP_400_BAD_REQUEST)
        assignment, created = assign_agent(issue, agent, request.user)
        return Response(
            serialize_assignment(assignment),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def delete(self, request, slug, project_id, issue_id):
        issue = self._issue(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Work item not found"}, status=status.HTTP_404_NOT_FOUND)
        agent = self._agent(request)
        if agent is None:
            return Response({"error": "unknown agent"}, status=status.HTTP_400_BAD_REQUEST)
        unassign_agent(issue, agent, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
