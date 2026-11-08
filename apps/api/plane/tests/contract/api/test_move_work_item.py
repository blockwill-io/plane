"""BlockWill fork — moving a work item between projects (plane/api/views/move.py).

Covers the images a description shows: an image uploaded through the generic
asset endpoint has a project and no issue, and was left in the old project on
a move, so the moved description showed "Error loading image".

Also covers who may move (PLAT-6): moving follows Plane's delete rule, so only
the item's creator or a source project admin may move it.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import FileAsset, Issue, Project, ProjectMember, State, User, WorkspaceMember
from plane.db.models.api import APIToken


def _project(workspace, user, name, identifier):
    project = Project.objects.create(name=name, identifier=identifier, workspace=workspace, created_by=user)
    ProjectMember.objects.create(project=project, member=user, role=20, is_active=True)
    State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)
    return project


def _image(workspace, user, project, name="plant.png"):
    return FileAsset.objects.create(
        attributes={"name": name, "type": "image/png", "size": 10},
        asset=f"{workspace.id}/{name}",
        size=10,
        workspace=workspace,
        project=project,
        created_by=user,
        entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
        is_uploaded=True,
        storage_metadata={"size": 10},
    )


def _with_image(asset):
    return f'<p>The plant.</p><image-component src="{asset.id}" id="{asset.id}" status="uploaded"></image-component>'


@pytest.fixture
def web(db, workspace, create_user):
    return _project(workspace, create_user, "Web App", "WEB")


@pytest.fixture
def unsorted(db, workspace, create_user):
    return _project(workspace, create_user, "Unsorted", "UNS")


@pytest.mark.contract
@pytest.mark.django_db
class TestMoveWorkItemDescriptionImages:
    def move(self, client, workspace, project, issue, target):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/move/"
        return client.post(url, {"target_project_id": str(target.id)}, format="json")

    def test_moves_an_image_the_description_shows(self, api_key_client, workspace, create_user, web, unsorted):
        asset = _image(workspace, create_user, web)
        issue = Issue.objects.create(
            name="Watering reminder",
            workspace=workspace,
            project=web,
            description_html=_with_image(asset),
            created_by=create_user,
        )

        response = self.move(api_key_client, workspace, web, issue, unsorted)

        assert response.status_code == status.HTTP_200_OK
        asset.refresh_from_db()
        assert asset.project_id == unsorted.id

    def test_leaves_an_image_another_description_still_shows(
        self, api_key_client, workspace, create_user, web, unsorted
    ):
        asset = _image(workspace, create_user, web)
        moving = Issue.objects.create(
            name="Moving", workspace=workspace, project=web, description_html=_with_image(asset), created_by=create_user
        )
        Issue.objects.create(
            name="Staying",
            workspace=workspace,
            project=web,
            description_html=_with_image(asset),
            created_by=create_user,
        )

        response = self.move(api_key_client, workspace, web, moving, unsorted)

        assert response.status_code == status.HTTP_200_OK
        asset.refresh_from_db()
        assert asset.project_id == web.id

    def test_ignores_a_malformed_src_and_still_moves(self, api_key_client, workspace, create_user, web, unsorted):
        issue = Issue.objects.create(
            name="Odd src",
            workspace=workspace,
            project=web,
            description_html='<image-component src="------------------------------------"></image-component>',
            created_by=create_user,
        )

        response = self.move(api_key_client, workspace, web, issue, unsorted)

        assert response.status_code == status.HTTP_200_OK

    def test_leaves_an_asset_another_entity_owns(self, api_key_client, workspace, create_user, web, unsorted):
        owner = Issue.objects.create(name="Owner", workspace=workspace, project=web, created_by=create_user)
        asset = _image(workspace, create_user, web)
        FileAsset.objects.filter(pk=asset.pk).update(issue=owner)
        issue = Issue.objects.create(
            name="Shows it",
            workspace=workspace,
            project=web,
            description_html=_with_image(asset),
            created_by=create_user,
        )

        response = self.move(api_key_client, workspace, web, issue, unsorted)

        assert response.status_code == status.HTTP_200_OK
        asset.refresh_from_db()
        assert asset.project_id == web.id

    def test_never_touches_an_asset_from_another_project(self, api_key_client, workspace, create_user, web, unsorted):
        elsewhere = _project(workspace, create_user, "Compliance", "CMP")
        asset = _image(workspace, create_user, elsewhere)
        issue = Issue.objects.create(
            name="Points elsewhere",
            workspace=workspace,
            project=web,
            description_html=_with_image(asset),
            created_by=create_user,
        )

        response = self.move(api_key_client, workspace, web, issue, unsorted)

        assert response.status_code == status.HTTP_200_OK
        asset.refresh_from_db()
        assert asset.project_id == elsewhere.id


@pytest.fixture
def member(db, workspace, web, unsorted):
    """A plain Member of both projects, with an API key."""
    user = User.objects.create(email="member@plane.so", username="member", first_name="Mem", last_name="Ber")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    ProjectMember.objects.create(project=web, member=user, role=15, is_active=True)
    ProjectMember.objects.create(project=unsorted, member=user, role=15, is_active=True)
    return user


def _client(user, token):
    APIToken.objects.create(user=user, label="Test", token=token)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token)
    return client


def _created_by(user, **fields):
    # BaseModel.save sets created_by from the request user, so set it after.
    issue = Issue.objects.create(**fields)
    Issue.objects.filter(pk=issue.pk).update(created_by=user)
    return issue


@pytest.mark.contract
@pytest.mark.django_db
class TestMoveWorkItemWhoMayMove:
    def move(self, client, workspace, project, issue, target):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/move/"
        return client.post(url, {"target_project_id": str(target.id)}, format="json")

    def test_member_cannot_move_someone_elses_item(self, workspace, create_user, web, unsorted, member):
        issue = _created_by(create_user, name="Admin's item", workspace=workspace, project=web)

        response = self.move(_client(member, "member-key"), workspace, web, issue, unsorted)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        issue.refresh_from_db()
        assert issue.project_id == web.id

    def test_member_can_move_own_item(self, workspace, web, unsorted, member):
        issue = _created_by(member, name="Own item", workspace=workspace, project=web)

        response = self.move(_client(member, "member-key"), workspace, web, issue, unsorted)

        assert response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.project_id == unsorted.id

    def test_source_admin_can_move_someone_elses_item(self, workspace, create_user, web, unsorted, member):
        issue = _created_by(member, name="Member's item", workspace=workspace, project=web)

        response = self.move(_client(create_user, "admin-key"), workspace, web, issue, unsorted)

        assert response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.project_id == unsorted.id

    def test_creator_still_needs_target_membership(self, workspace, create_user, web, member):
        private = _project(workspace, create_user, "Private", "PRV")
        issue = _created_by(member, name="Own item", workspace=workspace, project=web)

        response = self.move(_client(member, "member-key"), workspace, web, issue, private)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["error"] == "you must be a member of the target project"
        issue.refresh_from_db()
        assert issue.project_id == web.id
