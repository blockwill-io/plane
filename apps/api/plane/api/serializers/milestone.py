# BlockWill fork — v1 (public API) milestone serializers.

from plane.db.models import IssueMilestone, Milestone

from .base import BaseSerializer


class MilestoneAPISerializer(BaseSerializer):
    class Meta:
        model = Milestone
        fields = [
            "id",
            "title",
            "description",
            "target_date",
            "sort_order",
            "external_source",
            "external_id",
            "project",
            "workspace",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "project", "workspace", "created_at", "updated_at"]


class IssueMilestoneAPISerializer(BaseSerializer):
    class Meta:
        model = IssueMilestone
        fields = ["id", "issue", "milestone"]
        read_only_fields = fields
