"""BlockWill fork — moving a work item between projects (plane/api/views/move.py).

Covers the images a description shows: an image uploaded through the generic
asset endpoint has a project and no issue, and was left in the old project on
a move, so the moved description showed "Error loading image".
"""

import pytest
from rest_framework import status

from plane.db.models import FileAsset, Issue, Project, ProjectMember, State


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
