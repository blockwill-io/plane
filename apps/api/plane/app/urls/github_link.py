# BlockWill fork — GitHub link summary route (see views/github_link.py).

from django.urls import path

from plane.app.views import ProjectGithubLinkSummaryEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/github-links/",
        ProjectGithubLinkSummaryEndpoint.as_view(),
        name="project-github-links",
    ),
]
