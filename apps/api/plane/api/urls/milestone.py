# BlockWill fork — v1 milestone routes (SDK/MCP-compatible paths).

from django.urls import path

from plane.api.views import (
    MilestoneListCreateAPIEndpoint,
    MilestoneDetailAPIEndpoint,
    MilestoneWorkItemAPIEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/milestones/",
        MilestoneListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="milestones",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/milestones/<uuid:pk>/",
        MilestoneDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="milestone-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/milestones/<uuid:milestone_id>/work-items/",
        MilestoneWorkItemAPIEndpoint.as_view(http_method_names=["get", "post", "delete"]),
        name="milestone-work-items",
    ),
]
