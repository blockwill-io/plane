# BlockWill fork addition — agent assignment ("Assign to StartupOS").
#
# Work items keep their human owner (assignees) and their state. Separately, a
# work item can be handed to an automated agent — today only StartupOS — which
# picks it up through the Plane MCP server. The hand-off is this join row: its
# presence means "assigned to <agent>", its absence means "not assigned". It is
# deliberately NOT a state and NOT a label: states describe progress and the
# agent moves them as it works; labels are per-project, renameable and
# deletable, so an agent could never trust one.
#
# Kept entirely in this file (plus a dedicated migration) so upstream model
# files are never edited and upstream merges stay clean.

from django.conf import settings
from django.db import models
from django.db.models import Q

from .project import ProjectBaseModel

# Known agents. Adding one is one line here; the UI and the MCP server read
# the key, the label is for humans.
AGENTS = {
    "startupos": "StartupOS",
}
AGENT_CHOICES = tuple(AGENTS.items())


def agent_label(agent: str) -> str:
    return AGENTS.get(agent, agent)


class IssueAgentAssignment(ProjectBaseModel):
    """A work item handed to an automated agent."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="agent_assignments")
    agent = models.CharField(max_length=64, choices=AGENT_CHOICES, default="startupos")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="agent_assignments_made",
    )

    class Meta:
        unique_together = ["issue", "agent", "deleted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "agent"],
                condition=Q(deleted_at__isnull=True),
                name="issue_agent_assignment_unique_when_deleted_at_null",
            )
        ]
        verbose_name = "Issue Agent Assignment"
        verbose_name_plural = "Issue Agent Assignments"
        db_table = "issue_agent_assignments"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.issue_id} -> {self.agent}"
