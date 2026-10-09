"""BlockWill fork — agent assignment ("Assign to StartupOS").

Covers the app endpoints the web UI uses, the v1 endpoints the MCP server
uses, the activity lines both record, and the `agent` work item filter.
"""

import pytest
from rest_framework import status

from plane.db.models import Issue, IssueActivity, IssueAgentAssignment, Project, ProjectMember, State
from plane.utils.filters.filter_backend import ComplexFilterBackend
from plane.utils.filters.filterset import IssueFilterSet


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Web", identifier="WEB", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def state(db, workspace, project):
    return State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)


@pytest.fixture
def issues(db, workspace, project, state, create_user):
    return [
        Issue.objects.create(
            name=f"Item {n}", workspace=workspace, project=project, state=state, created_by=create_user
        )
        for n in range(3)
    ]


class _FilterView:
    filterset_class = IssueFilterSet


def _filtered(filter_data):
    return ComplexFilterBackend().filter_queryset(None, Issue.issue_objects.all(), _FilterView(), filter_data)


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentAssignmentApp:
    def url(self, workspace, project, issue):
        return f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/agent-assignment/"

    def test_assign_unassign_round_trip(self, session_client, workspace, project, issues, create_user):
        issue = issues[0]
        url = self.url(workspace, project, issue)

        assert session_client.get(url).json() == {"agent": "startupos", "assigned": False, "assignment": None}

        response = session_client.post(url, {"agent": "startupos"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["agent"] == "startupos"
        assert body["agent_label"] == "StartupOS"
        assert body["assigned_by"] == str(create_user.id)
        assert body["issue_id"] == str(issue.id)

        # idempotent: a second assign is a 200 with the same row
        again = session_client.post(url, {"agent": "startupos"}, format="json")
        assert again.status_code == status.HTTP_200_OK
        assert again.json()["id"] == body["id"]
        assert IssueAgentAssignment.objects.filter(issue=issue).count() == 1

        assert session_client.get(url).json()["assignment"]["id"] == body["id"]

        response = session_client.delete(url + "?agent=startupos")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert session_client.get(url).json()["assigned"] is False
        assert not IssueAgentAssignment.objects.filter(issue=issue).exists()

        # activity: one line each way, naming the agent
        lines = list(
            IssueActivity.objects.filter(issue=issue, field="agent_assignment")
            .order_by("created_at")
            .values_list("verb", "old_value", "new_value", "comment")
        )
        assert lines == [
            ("created", None, "startupos", "assigned the work item to StartupOS"),
            ("deleted", "startupos", None, "unassigned the work item from StartupOS"),
        ]

    def test_unknown_agent_is_rejected(self, session_client, workspace, project, issues):
        response = session_client.post(self.url(workspace, project, issues[0]), {"agent": "hal9000"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_agent_defaults_to_startupos(self, session_client, workspace, project, issues):
        response = session_client.post(self.url(workspace, project, issues[0]), {}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["agent"] == "startupos"

    def test_project_summary_lists_only_assigned(self, session_client, workspace, project, issues):
        session_client.post(self.url(workspace, project, issues[1]), {}, format="json")
        response = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/agent-assignments/")
        assert response.status_code == status.HTTP_200_OK
        assert set(response.json()) == {str(issues[1].id)}

    def test_filter_by_agent(self, session_client, workspace, project, issues):
        session_client.post(self.url(workspace, project, issues[2]), {}, format="json")

        assert {i.id for i in _filtered({"agent": "startupos"})} == {issues[2].id}
        assert {i.id for i in _filtered({"agent__in": ["startupos"]})} == {issues[2].id}
        assert {i.id for i in _filtered({"not": {"agent": "startupos"}})} == {issues[0].id, issues[1].id}

        # an unassigned row stops matching; the soft-deleted join row must not leak through
        session_client.delete(self.url(workspace, project, issues[2]))
        assert list(_filtered({"agent": "startupos"})) == []


@pytest.mark.contract
@pytest.mark.django_db
class TestAgentAssignmentV1:
    @pytest.fixture(autouse=True)
    def local_cache(self, settings):
        # The v1 API key throttle counts hits in the cache; keep that in-process.
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

    def url(self, workspace, project, issue):
        return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/{issue.id}/agent-assignment/"

    def test_queue_and_flip(self, api_key_client, workspace, project, issues, create_user):
        queue_url = f"/api/v1/workspaces/{workspace.slug}/agent-assignments/?agent=startupos"
        assert api_key_client.get(queue_url).json() == {"agent": "startupos", "count": 0, "results": []}

        response = api_key_client.post(self.url(workspace, project, issues[0]), {}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["work_item"]["identifier"] == f"WEB-{issues[0].sequence_id}"

        queue = api_key_client.get(queue_url).json()
        assert queue["count"] == 1
        row = queue["results"][0]
        assert row["agent"] == "startupos"
        assert row["assigned_by"] == str(create_user.id)
        assert row["work_item"]["id"] == str(issues[0].id)
        assert row["work_item"]["state_group"] == "unstarted"
        assert row["work_item"]["project_identifier"] == "WEB"

        detail = api_key_client.get(self.url(workspace, project, issues[0])).json()
        assert detail["assigned"] is True

        response = api_key_client.delete(self.url(workspace, project, issues[0]) + "?agent=startupos")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"agent": "startupos", "removed": True}
        assert api_key_client.get(queue_url).json()["count"] == 0
        assert api_key_client.get(self.url(workspace, project, issues[0])).json()["assigned"] is False

    def test_unknown_agent_names_the_known_ones(self, api_key_client, workspace):
        response = api_key_client.get(f"/api/v1/workspaces/{workspace.slug}/agent-assignments/?agent=hal9000")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "startupos" in response.json()["error"]

    def test_app_and_v1_share_one_row(self, session_client, api_key_client, workspace, project, issues):
        # assigned from the web UI, visible to the MCP server, and vice versa
        session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issues[1].id}/agent-assignment/",
            {},
            format="json",
        )
        queue = api_key_client.get(f"/api/v1/workspaces/{workspace.slug}/agent-assignments/").json()
        assert [r["work_item"]["id"] for r in queue["results"]] == [str(issues[1].id)]
