"""BlockWill fork — who may delete a milestone through the v1 API (PLAT-7).

The v1 delete follows the app's rule: the milestone's creator, a project
admin, or a workspace admin who is a member of the project.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Milestone, Project, ProjectMember, User, WorkspaceMember
from plane.db.models.api import APIToken


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Web", identifier="WEB", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def member(db, workspace, project):
    """A plain Member of the project, with an API key."""
    user = User.objects.create(email="member@plane.so", username="member", first_name="Mem", last_name="Ber")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    ProjectMember.objects.create(project=project, member=user, role=15, is_active=True)
    return user


def _client(user, token):
    APIToken.objects.create(user=user, label="Test", token=token)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token)
    return client


def _milestone(project, user, title="Q4 launch"):
    milestone = Milestone.objects.create(title=title, project=project, workspace=project.workspace)
    # BaseModel.save sets created_by from the request user, so set it after.
    Milestone.objects.filter(pk=milestone.pk).update(created_by=user)
    return milestone


def _url(workspace, project, milestone):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/milestones/{milestone.id}/"


@pytest.mark.contract
@pytest.mark.django_db
class TestMilestoneDeleteV1:
    def test_member_cannot_delete_someone_elses_milestone(self, workspace, create_user, project, member):
        milestone = _milestone(project, create_user)

        response = _client(member, "member-key").delete(_url(workspace, project, milestone))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Milestone.objects.filter(pk=milestone.pk).exists()

    def test_member_can_delete_own_milestone(self, workspace, project, member):
        milestone = _milestone(project, member)

        response = _client(member, "member-key").delete(_url(workspace, project, milestone))

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Milestone.objects.filter(pk=milestone.pk).exists()

    def test_project_admin_can_delete_someone_elses_milestone(self, workspace, create_user, project, member):
        milestone = _milestone(project, member)

        response = _client(create_user, "admin-key").delete(_url(workspace, project, milestone))

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Milestone.objects.filter(pk=milestone.pk).exists()

    def test_workspace_admin_in_project_can_delete(self, workspace, create_user, project, member):
        milestone = _milestone(project, create_user)
        WorkspaceMember.objects.filter(workspace=workspace, member=member).update(role=20)

        response = _client(member, "member-key").delete(_url(workspace, project, milestone))

        assert response.status_code == status.HTTP_204_NO_CONTENT
