# BlockWill fork addition — project milestones (Linear-style checkpoints).
#
# Upstream Plane gates milestones behind EE and keeps their models in a closed
# repo. This is our own implementation. Kept entirely in this file (plus a
# dedicated migration) so it never touches upstream model files — the issue↔
# milestone link is a join table rather than a column on the Issue model, so
# upstream merges stay clean.

from django.db import models
from django.db.models import Q

from .project import ProjectBaseModel


class Milestone(ProjectBaseModel):
    """A named checkpoint within a project, with an optional target date.

    Work items are assigned to a milestone via IssueMilestone; a milestone's
    progress is the share of its work items whose state group is "completed".
    """

    title = models.CharField(max_length=255, verbose_name="Milestone Title")
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    sort_order = models.FloatField(default=65535)
    external_source = models.CharField(max_length=255, null=True, blank=True)
    external_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ["title", "project", "deleted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["title", "project"],
                condition=Q(deleted_at__isnull=True),
                name="milestone_unique_title_project_when_deleted_at_null",
            )
        ]
        verbose_name = "Milestone"
        verbose_name_plural = "Milestones"
        db_table = "milestones"
        ordering = ("sort_order",)

    def __str__(self):
        return self.title


class IssueMilestone(ProjectBaseModel):
    """Join row linking a work item to a milestone."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="issue_milestone")
    milestone = models.ForeignKey(Milestone, on_delete=models.CASCADE, related_name="milestone_issues")

    class Meta:
        unique_together = ["issue", "milestone", "deleted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "milestone"],
                condition=Q(deleted_at__isnull=True),
                name="issue_milestone_unique_when_deleted_at_null",
            )
        ]
        verbose_name = "Issue Milestone"
        verbose_name_plural = "Issue Milestones"
        db_table = "issue_milestones"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.issue_id} {self.milestone_id}"
