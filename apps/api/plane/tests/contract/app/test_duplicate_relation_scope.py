"""BlockWill fork — marking a work item as a duplicate (PLAT-3).

Marking "Duplicate of" cancels the URL work item. The URL item must belong to
the URL project and workspace, in the app and the v1 API, so an ID from
another project or workspace is a 404 with nothing written.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Issue, IssueRelation, Project, ProjectMember, State, Workspace
from plane.db.models.api import APIToken
from plane.utils.duplicate_automation import cancel_duplicate_issue


def _project(workspace, user, name, identifier):
    project = Project.objects.create(name=name, identifier=identifier, workspace=workspace, created_by=user)
    ProjectMember.objects.create(project=project, member=user, role=20, is_active=True)
    State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)
    State.objects.create(name="Cancelled", project=project, workspace=workspace, group="cancelled")
    return project


def _issue(project, user, name):
    state = State.objects.get(project=project, group="unstarted")
    return Issue.objects.create(name=name, workspace=project.workspace, project=project, state=state, created_by=user)


@pytest.fixture
def v1_client(db, create_user):
    # Its own API key, so these requests do not use up the shared test key's rate limit.
    APIToken.objects.create(user=create_user, label="Test", token="relation-key")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY="relation-key")
    return client


@pytest.fixture
def web(db, workspace, create_user):
    return _project(workspace, create_user, "Web", "WEB")


@pytest.fixture
def other_project(db, workspace, create_user):
    # same workspace, and the caller is not a member
    return Project.objects.create(name="Ops", identifier="OPS", workspace=workspace, created_by=create_user)


@pytest.fixture
def victim_workspace(db, create_user):
    return Workspace.objects.create(name="Victim", owner=create_user, slug="victim-co")


def _victim_issue(workspace, user, name="Victim item"):
    project = Project.objects.create(name="Victim", identifier="VIC", workspace=workspace, created_by=user)
    State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)
    State.objects.create(name="Cancelled", project=project, workspace=workspace, group="cancelled")
    return _issue(project, user, name)


def _app_url(workspace, project, issue):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/issue-relation/"


def _v1_url(workspace, project, issue):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/{issue.id}/relations/"


@pytest.mark.contract
@pytest.mark.django_db
class TestDuplicateRelationScope:
    @pytest.mark.parametrize("which", ["app", "v1"])
    def test_marks_own_item_duplicate_and_cancels_it(
        self, which, session_client, v1_client, workspace, create_user, web
    ):
        dupe = _issue(web, create_user, "Dupe")
        canonical = _issue(web, create_user, "Canonical")
        client, url = (
            (session_client, _app_url(workspace, web, dupe))
            if which == "app"
            else (v1_client, _v1_url(workspace, web, dupe))
        )

        response = client.post(url, {"relation_type": "duplicate", "issues": [str(canonical.id)]}, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        dupe.refresh_from_db()
        assert dupe.state.group == "cancelled"

    @pytest.mark.parametrize("which", ["app", "v1"])
    def test_item_from_another_workspace_is_404(
        self, which, session_client, v1_client, workspace, create_user, web, victim_workspace
    ):
        victim = _victim_issue(victim_workspace, create_user)
        mine = _issue(web, create_user, "Mine")
        client, url = (
            (session_client, _app_url(workspace, web, victim))
            if which == "app"
            else (v1_client, _v1_url(workspace, web, victim))
        )

        response = client.post(url, {"relation_type": "duplicate", "issues": [str(mine.id)]}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        victim.refresh_from_db()
        assert victim.state.group == "unstarted"
        assert not IssueRelation.objects.filter(issue_id=victim.id).exists()

    @pytest.mark.parametrize("which", ["app", "v1"])
    def test_item_from_another_project_is_404(
        self, which, session_client, v1_client, workspace, create_user, web, other_project
    ):
        State.objects.create(name="Todo", project=other_project, workspace=workspace, group="unstarted", default=True)
        State.objects.create(name="Cancelled", project=other_project, workspace=workspace, group="cancelled")
        theirs = _issue(other_project, create_user, "Theirs")
        mine = _issue(web, create_user, "Mine")
        client, url = (
            (session_client, _app_url(workspace, web, theirs))
            if which == "app"
            else (v1_client, _v1_url(workspace, web, theirs))
        )

        response = client.post(url, {"relation_type": "duplicate", "issues": [str(mine.id)]}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        theirs.refresh_from_db()
        assert theirs.state.group == "unstarted"
        assert not IssueRelation.objects.filter(issue_id=theirs.id).exists()

    def test_helper_ignores_an_item_outside_the_given_project(self, workspace, create_user, web, victim_workspace):
        victim = _victim_issue(victim_workspace, create_user)

        assert cancel_duplicate_issue(victim.id, create_user, web.id, workspace.slug) is None
        victim.refresh_from_db()
        assert victim.state.group == "unstarted"
