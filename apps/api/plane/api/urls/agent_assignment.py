# BlockWill fork — v1 agent assignment routes (see views/agent_assignment.py).

from django.urls import path

from plane.api.views import WorkItemAgentAssignmentAPIEndpoint, WorkspaceAgentAssignmentListAPIEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/agent-assignments/",
        WorkspaceAgentAssignmentListAPIEndpoint.as_view(http_method_names=["get"]),
        name="workspace-agent-assignments",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:pk>/agent-assignment/",
        WorkItemAgentAssignmentAPIEndpoint.as_view(http_method_names=["get", "post", "delete"]),
        name="work-item-agent-assignment",
    ),
]
