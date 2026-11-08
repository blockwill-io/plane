"""BlockWill fork — restricted guests in the fork's project views (PLAT-5).

A project guest without guest_view_all_features sees only the work items they
created, as in IssueViewSet.list. Covers milestone items and list, throughput,
the GitHub link and agent summaries, and the v1 milestone work items.
"""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    IssueLink,
    IssueMilestone,
    Milestone,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)
from plane.db.models.api import APIToken
from plane.utils.agent_assignment import assign_agent


@pytest.fixture(autouse=True)
def local_cache(settings):
    # The v1 API key throttle counts hits in the cache; keep that in-process.
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.fixture
def setup(db, workspace, create_user):
    """Project WEB with admin (create_user) and guest; one item each, both in a
    milestone, completed, linked to a PR and handed to the agent."""
    project = Project.objects.create(name="Web", identifier="WEB", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    guest = User.objects.create(email="guest@plane.so", username="guest")
    WorkspaceMember.objects.create(workspace=workspace, member=guest, role=5)
    ProjectMember.objects.create(project=project, member=guest, role=5, is_active=True)

    done = State.objects.create(name="Done", project=project, workspace=workspace, group="completed")
    milestone = Milestone.objects.create(title="M1", project=project, workspace=workspace)
    items = {}
    for key, owner in (("admin", create_user), ("guest", guest)):
        issue = Issue.objects.create(name=f"{key} item", workspace=workspace, project=project, state=done)
        # save() resets created_by outside a request
        Issue.objects.filter(pk=issue.pk).update(created_by=owner, completed_at=timezone.now())
        IssueMilestone.objects.create(issue=issue, milestone=milestone, project=project, workspace=workspace)
        IssueLink.objects.create(
            issue=issue,
            url=f"https://github.com/example/repo/pull/{issue.sequence_id}",
            title="PR",
            project=project,
            workspace=workspace,
        )
        assign_agent(issue, "startupos", create_user)
        items[key] = str(issue.id)
    return {"project": project, "guest": guest, "milestone": milestone, "items": items}


def seen(user, workspace, setup):
    """The work item ids each view returns to `user`."""
    client = APIClient()
    client.force_authenticate(user=user)
    v1 = APIClient()
    v1.credentials(HTTP_X_API_KEY=APIToken.objects.create(user=user, label="t", token=f"key-{user.id}").token)
    base = f"/api/workspaces/{workspace.slug}/projects/{setup['project'].id}"
    milestone = setup["milestone"]
    milestones = client.get(f"{base}/milestones/").json()
    throughput = client.get(f"/api/workspaces/{workspace.slug}/analytics/throughput/").json()
    v1_rows = v1.get(
        f"/api/v1/workspaces/{workspace.slug}/projects/{setup['project'].id}/milestones/{milestone.id}/work-items/"
    ).json()["results"]
    return {
        "milestone_items": {i["id"] for i in client.get(f"{base}/milestones/{milestone.id}/milestone-issues/").json()},
        "milestone_list": {str(i) for i in milestones[0]["issue_ids"]},
        "milestone_total": {milestones[0]["total_issues"]},
        "throughput": {w["id"] for b in throughput["by_assignee"] for w in b["work_items"]},
        "github_links": set(client.get(f"{base}/github-links/").json()),
        "agent_summary": set(client.get(f"{base}/agent-assignments/").json()),
        "v1_milestone_items": {str(r["issue"]) for r in v1_rows},
    }


def expect(ids):
    return {
        "milestone_items": ids,
        "milestone_list": ids,
        "milestone_total": {len(ids)},
        "throughput": ids,
        "github_links": ids,
        "agent_summary": ids,
        "v1_milestone_items": ids,
    }


@pytest.mark.contract
@pytest.mark.django_db
class TestRestrictedGuestVisibility:
    def test_restricted_guest_sees_only_own_items(self, workspace, setup):
        assert seen(setup["guest"], workspace, setup) == expect({setup["items"]["guest"]})

    def test_guest_with_view_all_sees_everything(self, workspace, setup):
        Project.objects.filter(pk=setup["project"].pk).update(guest_view_all_features=True)
        assert seen(setup["guest"], workspace, setup) == expect(set(setup["items"].values()))

    def test_admin_sees_everything(self, workspace, setup, create_user):
        assert seen(create_user, workspace, setup) == expect(set(setup["items"].values()))
