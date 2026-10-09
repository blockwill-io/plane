# BlockWill fork — agent assignment routes (see views/agent_assignment.py).

from django.urls import path

from plane.app.views import IssueAgentAssignmentEndpoint, ProjectAgentAssignmentSummaryEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/agent-assignments/",
        ProjectAgentAssignmentSummaryEndpoint.as_view(),
        name="project-agent-assignments",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/agent-assignment/",
        IssueAgentAssignmentEndpoint.as_view(),
        name="issue-agent-assignment",
    ),
]
