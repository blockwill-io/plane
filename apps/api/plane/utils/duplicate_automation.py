# BlockWill fork addition — Linear-style duplicate handling.
#
# Two behaviors upstream Plane lacks:
#   1. Marking a work item "Duplicate of X" also cancels it (moves it to the
#      project's "Duplicate" state, falling back to the cancelled group's
#      first state) — but only while the item is still open, so linking an
#      already-finished item never rewrites history.
#   2. Declining an intake item as a duplicate also records the symmetric
#      duplicate relation, so the canonical ticket shows the link.
#
# Kept in its own file so upstream merges never conflict.

from django.utils import timezone

from plane.db.models import Issue, IssueActivity, IssueRelation, State

OPEN_STATE_GROUPS = ("backlog", "unstarted", "started")


def cancel_duplicate_issue(issue_id, actor):
    """Move a work item that was just marked as a duplicate into its
    project's "Duplicate" state (or the cancelled group's first state).

    No-op when the item is already completed/cancelled, or when no suitable
    state exists. Returns the new state or None.
    """
    issue = Issue.objects.filter(pk=issue_id).select_related("state").first()
    if issue is None or issue.state is None:
        return None
    if issue.state.group not in OPEN_STATE_GROUPS:
        return None

    target = (
        State.objects.filter(project_id=issue.project_id, name__iexact="duplicate")
        .exclude(group="triage")
        .first()
        or State.objects.filter(project_id=issue.project_id, group="cancelled").order_by("sequence").first()
    )
    if target is None or target.id == issue.state_id:
        return None

    old_state = issue.state
    issue.state = target
    issue.save()

    IssueActivity.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        actor=actor,
        verb="updated",
        field="state",
        old_value=old_state.name,
        new_value=target.name,
        old_identifier=old_state.id,
        new_identifier=target.id,
        comment=f"moved the work item to {target.name} because it was marked as a duplicate",
        epoch=timezone.now().timestamp(),
    )
    return target


def link_intake_duplicate(intake_issue, actor):
    """Record the symmetric duplicate relation for an intake item that was
    declined as a duplicate, so the canonical ticket shows the link."""
    if intake_issue.status != 2 or intake_issue.duplicate_to_id is None:
        return None
    if intake_issue.duplicate_to_id == intake_issue.issue_id:
        return None

    existing = IssueRelation.objects.filter(
        issue_id__in=[intake_issue.issue_id, intake_issue.duplicate_to_id],
        related_issue_id__in=[intake_issue.issue_id, intake_issue.duplicate_to_id],
    ).exists()
    if existing:
        return None

    return IssueRelation.objects.create(
        issue_id=intake_issue.issue_id,
        related_issue_id=intake_issue.duplicate_to_id,
        relation_type="duplicate",
        project_id=intake_issue.project_id,
        workspace_id=intake_issue.workspace_id,
        created_by=actor,
        updated_by=actor,
    )
