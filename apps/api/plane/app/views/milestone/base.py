# BlockWill fork — milestone endpoints. See plane/db/models/milestone.py.

from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.fields import ArrayField
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, UUIDField, Value
from django.db.models.functions import Coalesce

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import IssueSerializer, MilestoneSerializer, MilestoneWriteSerializer
from plane.db.models import Issue, IssueMilestone, Milestone

from ..base import BaseViewSet


class MilestoneViewSet(BaseViewSet):
    model = Milestone
    serializer_class = MilestoneSerializer

    def get_serializer_class(self):
        return (
            MilestoneWriteSerializer
            if self.action in ["create", "update", "partial_update"]
            else MilestoneSerializer
        )

    def get_queryset(self):
        completed_issues = (
            Issue.issue_objects.filter(
                state__group="completed",
                issue_milestone__milestone_id=OuterRef("pk"),
                issue_milestone__deleted_at__isnull=True,
            )
            .values("issue_milestone__milestone_id")
            .annotate(cnt=Count("pk"))
            .values("cnt")
        )
        total_issues = (
            Issue.issue_objects.filter(
                issue_milestone__milestone_id=OuterRef("pk"),
                issue_milestone__deleted_at__isnull=True,
            )
            .values("issue_milestone__milestone_id")
            .annotate(cnt=Count("pk"))
            .values("cnt")
        )
        return (
            Milestone.objects.filter(
                workspace__slug=self.kwargs.get("slug"),
                project_id=self.kwargs.get("project_id"),
            )
            .annotate(completed_issues=Coalesce(Subquery(completed_issues[:1]), Value(0, output_field=IntegerField())))
            .annotate(total_issues=Coalesce(Subquery(total_issues[:1]), Value(0, output_field=IntegerField())))
            # The linked work item ids travel with the list response so the UI can
            # map issue -> milestone in one request (no per-milestone fetches).
            .annotate(
                issue_ids=Coalesce(
                    ArrayAgg(
                        "milestone_issues__issue_id",
                        distinct=True,
                        filter=Q(milestone_issues__deleted_at__isnull=True)
                        & Q(milestone_issues__issue__isnull=False),
                    ),
                    Value([], output_field=ArrayField(UUIDField())),
                )
            )
            .distinct()
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def create(self, request, slug, project_id):
        serializer = MilestoneWriteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(project_id=project_id)
            milestone = self.get_queryset().get(pk=serializer.data["id"])
            return Response(MilestoneSerializer(milestone).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def list(self, request, slug, project_id):
        milestones = self.get_queryset()
        return Response(MilestoneSerializer(milestones, many=True).data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def retrieve(self, request, slug, project_id, pk):
        milestone = self.get_queryset().filter(pk=pk).first()
        if milestone is None:
            return Response({"error": "Milestone not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(MilestoneSerializer(milestone).data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def partial_update(self, request, slug, project_id, pk):
        milestone = Milestone.objects.get(workspace__slug=slug, project_id=project_id, pk=pk)
        serializer = MilestoneWriteSerializer(milestone, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            updated = self.get_queryset().get(pk=pk)
            return Response(MilestoneSerializer(updated).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission([ROLE.ADMIN], creator=True, model=Milestone)
    def destroy(self, request, slug, project_id, pk):
        milestone = Milestone.objects.get(workspace__slug=slug, project_id=project_id, pk=pk)
        milestone.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MilestoneIssueViewSet(BaseViewSet):
    model = IssueMilestone

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def list(self, request, slug, project_id, milestone_id):
        issues = (
            Issue.issue_objects.filter(
                workspace__slug=slug,
                project_id=project_id,
                issue_milestone__milestone_id=milestone_id,
                issue_milestone__deleted_at__isnull=True,
            )
            .select_related("project", "workspace", "state", "parent")
            .prefetch_related("assignees", "labels")
            .distinct()
        )
        return Response(IssueSerializer(issues, many=True).data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def create(self, request, slug, project_id, milestone_id):
        issue_ids = request.data.get("issues", [])
        if not issue_ids:
            return Response({"error": "issues are required"}, status=status.HTTP_400_BAD_REQUEST)
        # Scope to real work items in this project; get_or_create keeps it idempotent.
        valid_ids = Issue.objects.filter(
            workspace__slug=slug, project_id=project_id, pk__in=issue_ids
        ).values_list("id", flat=True)
        for issue_id in valid_ids:
            IssueMilestone.objects.get_or_create(
                issue_id=issue_id,
                milestone_id=milestone_id,
                project_id=project_id,
            )
        return Response(status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def destroy(self, request, slug, project_id, milestone_id, issue_id):
        IssueMilestone.objects.filter(
            milestone_id=milestone_id, issue_id=issue_id, project_id=project_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
