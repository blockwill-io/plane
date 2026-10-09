# BlockWill fork addition — assign / unassign a work item to an agent.
#
# One place for the rule set, shared by the app API (web UI) and the v1 API
# (MCP server / StartupOS), so both record the same activity line and the
# work item's history reads the same whoever flipped it.

from django.utils import timezone

from plane.db.models import AGENTS, Issue, IssueActivity, IssueAgentAssignment, agent_label

ACTIVITY_FIELD = "agent_assignment"


def is_known_agent(agent: str) -> bool:
    return agent in AGENTS


def get_assignment(issue_id, agent: str):
    return IssueAgentAssignment.objects.filter(issue_id=issue_id, agent=agent).select_related("assigned_by").first()


def assign_agent(issue: Issue, agent: str, actor):
    """Hand the work item to `agent`. Idempotent: a second call returns the
    existing row and records nothing."""
    existing = get_assignment(issue.id, agent)
    if existing is not None:
        return existing, False

    assignment = IssueAgentAssignment.objects.create(
        issue=issue,
        agent=agent,
        assigned_by=actor,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
    )
    IssueActivity.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        actor=actor,
        verb="created",
        field=ACTIVITY_FIELD,
        old_value=None,
        new_value=agent,
        new_identifier=assignment.id,
        comment=f"assigned the work item to {agent_label(agent)}",
        epoch=timezone.now().timestamp(),
    )
    return assignment, True


def unassign_agent(issue: Issue, agent: str, actor):
    """Take the work item back from `agent`. Idempotent: returns False when
    there was nothing to remove."""
    assignment = get_assignment(issue.id, agent)
    if assignment is None:
        return False

    assignment.delete()
    IssueActivity.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        actor=actor,
        verb="deleted",
        field=ACTIVITY_FIELD,
        old_value=agent,
        new_value=None,
        old_identifier=assignment.id,
        comment=f"unassigned the work item from {agent_label(agent)}",
        epoch=timezone.now().timestamp(),
    )
    return True


def serialize_assignment(assignment) -> dict:
    """Wire shape shared by the app and v1 endpoints."""
    user = assignment.assigned_by
    return {
        "id": str(assignment.id),
        "issue_id": str(assignment.issue_id),
        "agent": assignment.agent,
        "agent_label": agent_label(assignment.agent),
        "assigned_by": str(user.id) if user else None,
        "assigned_by_display_name": user.display_name if user else None,
        "assigned_at": assignment.created_at,
    }
