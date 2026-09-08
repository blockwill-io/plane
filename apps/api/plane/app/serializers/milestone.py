# BlockWill fork — milestone serializers. See plane/db/models/milestone.py.

from rest_framework import serializers

from plane.db.models import Milestone, IssueMilestone

from .base import BaseSerializer, DynamicBaseSerializer


class MilestoneWriteSerializer(BaseSerializer):
    class Meta:
        model = Milestone
        fields = "__all__"
        read_only_fields = [
            "workspace",
            "project",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "deleted_at",
        ]


class MilestoneSerializer(DynamicBaseSerializer):
    # Progress: populated by the view's queryset annotations.
    total_issues = serializers.IntegerField(read_only=True)
    completed_issues = serializers.IntegerField(read_only=True)

    class Meta:
        model = Milestone
        fields = [
            "id",
            "title",
            "description",
            "target_date",
            "sort_order",
            "project_id",
            "workspace_id",
            "total_issues",
            "completed_issues",
            "external_source",
            "external_id",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = fields


class IssueMilestoneSerializer(BaseSerializer):
    class Meta:
        model = IssueMilestone
        fields = ["id", "issue", "milestone", "project_id", "workspace_id"]
        read_only_fields = ["workspace", "project"]
