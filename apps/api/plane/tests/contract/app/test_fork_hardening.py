"""BlockWill fork — small cross-project checks (PLAT-24).

- Linking work items to a milestone (app and v1) needs the URL milestone to be
  in the URL project, so another project's milestone counts cannot be inflated.
- Declining an intake item as a duplicate (app and v1) needs duplicate_to to be
  a work item in the intake item's own workspace and project.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Intake, IntakeIssue, Issue, IssueMilestone, Milestone, Project, ProjectMember, State
from plane.db.models.api import APIToken


def _project(workspace, user, name, identifier, member=True):
    project = Project.objects.create(name=name, identifier=identifier, workspace=workspace, created_by=user)
    if member:
        ProjectMember.objects.create(project=project, member=user, role=20, is_active=True)
    State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)
    return project


@pytest.fixture
def v1_client(db, create_user):
    # Its own API key, so these requests do not use up the shared test key's rate limit.
    APIToken.objects.create(user=create_user, label="Test", token="hardening-key")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY="hardening-key")
    return client


@pytest.fixture
def web(db, workspace, create_user):
    return _project(workspace, create_user, "Web", "WEB")


@pytest.fixture
def ops(db, workspace, create_user):
    # same workspace, and the caller is not a member
    return _project(workspace, create_user, "Ops", "OPS", member=False)


def _issue(project, name="Item"):
    return Issue.objects.create(name=name, workspace=project.workspace, project=project)


@pytest.mark.contract
@pytest.mark.django_db
class TestMilestoneLinkProjectScope:
    def app_url(self, workspace, project, milestone):
        return f"/api/workspaces/{workspace.slug}/projects/{project.id}/milestones/{milestone.id}/milestone-issues/"

    def v1_url(self, workspace, project, milestone):
        return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/milestones/{milestone.id}/work-items/"

    @pytest.mark.parametrize("which", ["app", "v1"])
    def test_links_to_own_milestone(self, which, session_client, v1_client, workspace, web):
        milestone = Milestone.objects.create(title="Launch", project=web, workspace=workspace)
        issue = _issue(web)
        client, url = (
            (session_client, self.app_url(workspace, web, milestone))
            if which == "app"
            else (v1_client, self.v1_url(workspace, web, milestone))
        )

        response = client.post(url, {"issues": [str(issue.id)]}, format="json")

        assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_204_NO_CONTENT)
        assert IssueMilestone.objects.filter(milestone=milestone, issue=issue).exists()

    @pytest.mark.parametrize("which", ["app", "v1"])
    def test_another_projects_milestone_is_404(self, which, session_client, v1_client, workspace, web, ops):
        theirs = Milestone.objects.create(title="Their launch", project=ops, workspace=workspace)
        issue = _issue(web)
        client, url = (
            (session_client, self.app_url(workspace, web, theirs))
            if which == "app"
            else (v1_client, self.v1_url(workspace, web, theirs))
        )

        response = client.post(url, {"issues": [str(issue.id)]}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not IssueMilestone.objects.filter(milestone=theirs).exists()


@pytest.fixture
def intake_item(db, workspace, create_user, web):
    intake = Intake.objects.create(name="Intake", project=web, workspace=workspace)
    triage = State.objects.create(name="Triage", project=web, workspace=workspace, group="triage")
    issue = Issue.objects.create(name="Request", workspace=workspace, project=web, state=triage)
    return IntakeIssue.objects.create(intake=intake, issue=issue, project=web, workspace=workspace)


@pytest.mark.contract
@pytest.mark.django_db
class TestIntakeDuplicateScope:
    def patch(self, which, session_client, v1_client, workspace, project, intake_item, duplicate_to):
        body = {"status": 2, "duplicate_to": str(duplicate_to.id)}
        if which == "app":
            url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/intake-issues/{intake_item.issue_id}/"
            return session_client.patch(url, body, format="json")
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/intake-issues/{intake_item.issue_id}/"
        return v1_client.patch(url, body, format="json")

    @pytest.mark.parametrize("which", ["app", "v1"])
    def test_duplicate_of_item_in_same_project(self, which, session_client, v1_client, workspace, web, intake_item):
        canonical = _issue(web, "Canonical")

        response = self.patch(which, session_client, v1_client, workspace, web, intake_item, canonical)

        assert response.status_code == status.HTTP_200_OK
        intake_item.refresh_from_db()
        assert intake_item.duplicate_to_id == canonical.id

    @pytest.mark.parametrize("which", ["app", "v1"])
    def test_duplicate_of_item_in_another_project_is_400(
        self, which, session_client, v1_client, workspace, web, ops, intake_item
    ):
        theirs = _issue(ops, "Theirs")

        response = self.patch(which, session_client, v1_client, workspace, web, intake_item, theirs)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        intake_item.refresh_from_db()
        assert intake_item.duplicate_to_id is None
        assert intake_item.status != 2
