# BlockWill fork — v1 (public API) milestone endpoints. Path shape matches the
# plane-sdk / MCP milestone tool so it works against these without changes.

from rest_framework import status
from rest_framework.response import Response

from plane.api.serializers import IssueMilestoneAPISerializer, MilestoneAPISerializer
from plane.app.permissions import ProjectEntityPermission
from plane.db.models import Issue, IssueMilestone, Milestone

from .base import BaseAPIView


class MilestoneListCreateAPIEndpoint(BaseAPIView):
    """List and create milestones for a project."""

    serializer_class = MilestoneAPISerializer
    model = Milestone
    permission_classes = [ProjectEntityPermission]

    def get_queryset(self):
        return Milestone.objects.filter(
            workspace__slug=self.kwargs.get("slug"),
            project_id=self.kwargs.get("project_id"),
        ).distinct()

    def get(self, request, slug, project_id):
        return self.paginate(
            request=request,
            queryset=self.get_queryset(),
            on_results=lambda milestones: MilestoneAPISerializer(milestones, many=True).data,
        )

    def post(self, request, slug, project_id):
        serializer = MilestoneAPISerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(project_id=project_id)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MilestoneDetailAPIEndpoint(BaseAPIView):
    """Retrieve, update or delete a milestone."""

    serializer_class = MilestoneAPISerializer
    model = Milestone
    permission_classes = [ProjectEntityPermission]

    def _get(self, slug, project_id, pk):
        return Milestone.objects.filter(workspace__slug=slug, project_id=project_id, pk=pk).first()

    def get(self, request, slug, project_id, pk):
        milestone = self._get(slug, project_id, pk)
        if milestone is None:
            return Response({"error": "Milestone not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(MilestoneAPISerializer(milestone).data, status=status.HTTP_200_OK)

    def patch(self, request, slug, project_id, pk):
        milestone = self._get(slug, project_id, pk)
        if milestone is None:
            return Response({"error": "Milestone not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = MilestoneAPISerializer(milestone, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug, project_id, pk):
        milestone = self._get(slug, project_id, pk)
        if milestone is None:
            return Response({"error": "Milestone not found"}, status=status.HTTP_404_NOT_FOUND)
        milestone.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MilestoneWorkItemAPIEndpoint(BaseAPIView):
    """List, add and remove the work items of a milestone."""

    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, milestone_id):
        return self.paginate(
            request=request,
            queryset=IssueMilestone.objects.filter(
                workspace__slug=slug, project_id=project_id, milestone_id=milestone_id
            ),
            on_results=lambda rows: IssueMilestoneAPISerializer(rows, many=True).data,
        )

    def post(self, request, slug, project_id, milestone_id):
        issue_ids = request.data.get("issues", [])
        if not issue_ids:
            return Response({"error": "issues are required"}, status=status.HTTP_400_BAD_REQUEST)
        valid_ids = Issue.objects.filter(
            workspace__slug=slug, project_id=project_id, pk__in=issue_ids
        ).values_list("id", flat=True)
        for issue_id in valid_ids:
            IssueMilestone.objects.get_or_create(
                issue_id=issue_id, milestone_id=milestone_id, project_id=project_id
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, slug, project_id, milestone_id):
        issue_ids = request.data.get("issues", [])
        qs = IssueMilestone.objects.filter(
            workspace__slug=slug, project_id=project_id, milestone_id=milestone_id
        )
        if issue_ids:
            qs = qs.filter(issue_id__in=issue_ids)
        qs.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
