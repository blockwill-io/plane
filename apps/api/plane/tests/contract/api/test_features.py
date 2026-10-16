"""BlockWill fork — workspace and project feature flags on the v1 API."""

import pytest
from rest_framework import status

from plane.db.models import Project, ProjectMember, WorkspaceMember


@pytest.fixture(autouse=True)
def local_cache(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "features"}}


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Web", identifier="WEB", workspace=workspace, created_by=create_user, cycle_view=True
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkspaceFeatures:
    def url(self, workspace):
        return f"/api/v1/workspaces/{workspace.slug}/features/"

    def test_everything_reads_false(self, api_key_client, workspace):
        body = api_key_client.get(self.url(workspace)).json()
        assert body["initiatives"] is False and body["releases"] is False
        assert body["states_owned_by_workspace"] is False

    def test_turning_a_paid_module_on_is_refused(self, api_key_client, workspace):
        response = api_key_client.patch(self.url(workspace), {"initiatives": True}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not available" in response.json()["error"]
        assert api_key_client.patch(self.url(workspace), {"initiatives": False}, format="json").status_code == 200


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectFeatures:
    def url(self, workspace, project):
        return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/features/"

    def test_reads_the_real_toggles(self, api_key_client, workspace, project):
        body = api_key_client.get(self.url(workspace, project)).json()
        assert body["cycles"] is True and body["modules"] is False and body["pages"] is True
        assert body["epics"] is False

    def test_patch_flips_the_project_columns(self, api_key_client, workspace, project):
        response = api_key_client.patch(self.url(workspace, project), {"modules": True, "cycles": False}, format="json")
        assert response.status_code == 200
        assert response.json()["modules"] is True and response.json()["cycles"] is False
        project.refresh_from_db()
        assert project.module_view is True and project.cycle_view is False

    def test_patch_rejects_unavailable_and_unknown(self, api_key_client, workspace, project):
        url = self.url(workspace, project)
        assert api_key_client.patch(url, {"epics": True}, format="json").status_code == 400
        assert api_key_client.patch(url, {"colour": True}, format="json").status_code == 400
        assert api_key_client.patch(url, {"cycles": "yes"}, format="json").status_code == 400

    def test_non_admin_member_cannot_patch(self, api_key_client, workspace, project, create_user):
        # Plane's rule: project admins, or workspace admins who are in the project.
        ProjectMember.objects.filter(project=project, member=create_user).update(role=15)
        WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)
        response = api_key_client.patch(self.url(workspace, project), {"modules": True}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
