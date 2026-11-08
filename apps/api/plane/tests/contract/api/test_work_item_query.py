"""BlockWill fork — PQL and the workspace list/count endpoints.

Covers the PQL compiler (plane/utils/pql.py) directly, and the v1 endpoints
the Plane MCP server's `workitem list` / `list_archived` / `count` call.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework import status

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueRelation,
    Label,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)
from plane.utils.pql import PQLError, compile_pql, work_item_base_queryset


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Web", identifier="WEB", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def states(db, workspace, project):
    return {
        group: State.objects.create(name=group.title(), project=project, workspace=workspace, group=group)
        for group in ("backlog", "unstarted", "started", "completed")
    }


@pytest.fixture
def other_user(db, workspace):
    user = User.objects.create(email="other@plane.so", username="other")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    return user


@pytest.fixture
def bug_label(db, workspace, project):
    return Label.objects.create(name="bug", project=project, workspace=workspace)


@pytest.fixture
def items(db, workspace, project, states, create_user, other_user, bug_label):
    """WEB-1 urgent/started, mine, bug, overdue
    WEB-2 high/backlog, other's, child of WEB-1
    WEB-3 low/completed, unassigned, overdue but closed
    WEB-4 none/unstarted, unassigned, blocked by WEB-1"""
    today = timezone.now().date()

    def make(name, priority, state, **extra):
        return Issue.objects.create(
            name=name,
            priority=priority,
            state=states[state],
            workspace=workspace,
            project=project,
            created_by=create_user,
            **extra,
        )

    one = make("Fix login capex bug", "urgent", "started", target_date=today - timedelta(days=2))
    two = make("Polish signup", "high", "backlog", parent=one)
    three = make("Ship docs", "low", "completed", target_date=today - timedelta(days=5))
    four = make("Plan launch", "none", "unstarted")

    for issue, user in ((one, create_user), (two, other_user)):
        IssueAssignee.objects.create(issue=issue, assignee=user, project=project, workspace=workspace)
    IssueLabel.objects.create(issue=one, label=bug_label, project=project, workspace=workspace)
    IssueRelation.objects.create(
        issue=four, related_issue=one, relation_type="blocked_by", project=project, workspace=workspace
    )
    return {"one": one, "two": two, "three": three, "four": four}


def names(pql, workspace, user, project_id=None):
    q, hidden = compile_pql(pql, workspace.slug, user, project_id)
    return sorted(
        work_item_base_queryset(hidden).filter(workspace=workspace).filter(q).distinct().values_list("name", flat=True)
    )


@pytest.mark.contract
@pytest.mark.django_db
class TestPQLCompiler:
    def test_fields_and_functions(self, workspace, create_user, items, bug_label):
        u = create_user
        assert names('priority = "urgent"', workspace, u) == ["Fix login capex bug"]
        assert names('priority IN ("high", "urgent")', workspace, u) == ["Fix login capex bug", "Polish signup"]
        assert names("stateGroup IN openStates()", workspace, u) == [
            "Fix login capex bug",
            "Plan launch",
            "Polish signup",
        ]
        assert names("assignee = currentUser()", workspace, u) == ["Fix login capex bug"]
        assert names("hasNoAssignee()", workspace, u) == ["Plan launch", "Ship docs"]
        assert names("isOverdue()", workspace, u) == ["Fix login capex bug"]
        assert names('title ~ "capex"', workspace, u) == ["Fix login capex bug"]
        assert names('id = "WEB-2"', workspace, u) == ["Polish signup"]
        assert names(f'label = "{bug_label.id}"', workspace, u) == ["Fix login capex bug"]
        # != on a many-valued field means "has no such row", unlabeled included
        assert names(f'label != "{bug_label.id}"', workspace, u) == ["Plan launch", "Polish signup", "Ship docs"]
        assert names("dueDate BETWEEN (daysAgo(3), today())", workspace, u) == ["Fix login capex bug"]
        assert names("dueDate IS NULL", workspace, u) == ["Plan launch", "Polish signup"]
        assert names("createdAt >= startOfWeek()", workspace, u) == sorted(i.name for i in items.values())

    def test_relations(self, workspace, create_user, items):
        u = create_user
        assert names('childOf("WEB-1")', workspace, u) == ["Polish signup"]
        assert names('parentOf("WEB-2")', workspace, u) == ["Fix login capex bug"]
        assert names('blockedBy("WEB-1")', workspace, u) == ["Plan launch"]
        assert names('blocks("WEB-4")', workspace, u) == ["Fix login capex bug"]
        assert names("isTopLevel() AND hasChildren()", workspace, u) == ["Fix login capex bug"]

    def test_boolean_logic(self, workspace, create_user, items):
        u = create_user
        # AND binds tighter than OR
        assert names('priority = "low" OR priority = "urgent" AND assignee = currentUser()', workspace, u) == [
            "Fix login capex bug",
            "Ship docs",
        ]
        assert names('NOT (priority = "urgent" OR stateGroup = "completed")', workspace, u) == [
            "Plan launch",
            "Polish signup",
        ]
        assert names('priority NOT IN ("urgent", "none")', workspace, u) == ["Polish signup", "Ship docs"]

    def test_archived_and_draft_are_opt_in(self, workspace, create_user, items):
        items["three"].archived_at = timezone.now().date()
        items["three"].save()
        assert "Ship docs" not in names('priority = "low" OR priority = "urgent"', workspace, create_user)
        assert names("isArchived()", workspace, create_user) == ["Ship docs"]

    @pytest.mark.parametrize(
        "pql, message",
        [
            ('prio = "high"', "Unknown field"),
            ('priority = "critical"', "priority must be one of"),
            ('assignee = "bhavya"', "needs a UUID"),
            ('cf["abc"] = "x"', "Custom properties"),
            ('priority = "high" AND', "Expected"),
            ('childOf("NOPE-99")', "was not found"),
            ("", "Empty"),
        ],
    )
    def test_errors_explain_themselves(self, workspace, create_user, items, pql, message):
        with pytest.raises(PQLError, match=message):
            compile_pql(pql, workspace.slug, create_user)


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkItemQueryV1:
    @pytest.fixture(autouse=True)
    def local_cache(self, settings):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

    def test_project_list_takes_pql(self, api_key_client, workspace, project, items):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"
        body = api_key_client.get(url, {"pql": "stateGroup IN openStates() AND hasNoAssignee()"}).json()
        assert [r["name"] for r in body["results"]] == ["Plan launch"]
        assert body["total_count"] == 1

        assert len(api_key_client.get(url).json()["results"]) == 4

    def test_bad_pql_is_a_400_with_a_pql_key(self, api_key_client, workspace, project, items):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"
        response = api_key_client.get(url, {"pql": 'nope = "x"'})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unknown field" in response.json()["pql"]

    def test_structured_filters(self, api_key_client, workspace, project, items):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/"
        body = api_key_client.get(url, {"filters": '{"state_group__in": "completed"}'}).json()
        assert [r["name"] for r in body["results"]] == ["Ship docs"]

    def test_workspace_list(self, api_key_client, workspace, project, items):
        url = f"/api/v1/workspaces/{workspace.slug}/work-items/"
        body = api_key_client.get(url, {"pql": 'priority = "urgent"'}).json()
        assert [r["name"] for r in body["results"]] == ["Fix login capex bug"]
        assert len(api_key_client.get(url).json()["results"]) == 4

    def test_workspace_list_hides_projects_you_are_not_in(self, api_key_client, workspace, project, items, other_user):
        hidden = Project.objects.create(name="Secret", identifier="SEC", workspace=workspace, created_by=other_user)
        Issue.objects.create(name="Secret thing", workspace=workspace, project=hidden, created_by=other_user)
        url = f"/api/v1/workspaces/{workspace.slug}/work-items/"
        assert "Secret thing" not in [r["name"] for r in api_key_client.get(url).json()["results"]]

    def test_archived_list(self, api_key_client, workspace, project, items):
        items["three"].archived_at = timezone.now().date()
        items["three"].save()
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/archived-work-items/"
        assert [r["name"] for r in api_key_client.get(url).json()["results"]] == ["Ship docs"]

    def test_count(self, api_key_client, workspace, project, items, bug_label, create_user, other_user):
        url = f"/api/v1/workspaces/{workspace.slug}/work-items/count/"

        assert api_key_client.get(url).json() == {
            "grouped_by": None,
            "sub_grouped_by": None,
            "total_count": 4,
            "grouped_counts": {},
        }

        body = api_key_client.get(url, {"group_by": "state__group", "pql": "stateGroup IN openStates()"}).json()
        assert body["total_count"] == 3
        assert body["grouped_counts"] == {
            "backlog": {"count": 1},
            "started": {"count": 1},
            "unstarted": {"count": 1},
        }

        body = api_key_client.get(url, {"group_by": "assignees__id", "sub_group_by": "priority"}).json()
        assert body["grouped_counts"] == {
            "None": {"count": 2, "sub_grouped_counts": {"low": {"count": 1}, "none": {"count": 1}}},
            str(create_user.id): {"count": 1, "sub_grouped_counts": {"urgent": {"count": 1}}},
            str(other_user.id): {"count": 1, "sub_grouped_counts": {"high": {"count": 1}}},
        }

        body = api_key_client.get(url, {"group_by": "labels__id"}).json()
        assert body["grouped_counts"] == {"None": {"count": 3}, str(bug_label.id): {"count": 1}}

    def test_count_rejects_unknown_grouping(self, api_key_client, workspace, items):
        url = f"/api/v1/workspaces/{workspace.slug}/work-items/count/"
        assert api_key_client.get(url, {"group_by": "colour"}).status_code == status.HTTP_400_BAD_REQUEST
        assert api_key_client.get(url, {"sub_group_by": "priority"}).status_code == status.HTTP_400_BAD_REQUEST
        response = api_key_client.get(url, {"pql": f'state = "{uuid4()}" AND'})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "pql" in response.json()


@pytest.mark.contract
@pytest.mark.django_db
class TestPQLVisibility:
    """PLAT-17: lookups inside a query only see what the caller can see, and
    over-deep nesting is refused."""

    @pytest.fixture
    def secret(self, workspace, other_user):
        project = Project.objects.create(name="Secret", identifier="SEC", workspace=workspace, created_by=other_user)
        ProjectMember.objects.create(project=project, member=other_user, role=20, is_active=True)
        Issue.objects.create(name="Secret thing", workspace=workspace, project=project)
        return project

    @pytest.fixture
    def guest(self, workspace, project):
        user = User.objects.create(email="guest@plane.so", username="guest")
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=5)
        ProjectMember.objects.create(project=project, member=user, role=5, is_active=True)
        return user

    def test_relation_lookups_skip_hidden_projects(self, workspace, create_user, other_user, items, secret):
        with pytest.raises(PQLError, match='"SEC-1" was not found'):
            compile_pql('childOf("SEC-1")', workspace.slug, create_user)
        # the project's own member still resolves it
        compile_pql('childOf("SEC-1")', workspace.slug, other_user)

    def test_relation_lookups_follow_guest_rule(self, workspace, project, items, guest):
        with pytest.raises(PQLError, match="was not found"):
            compile_pql('childOf("WEB-1")', workspace.slug, guest)
        Project.objects.filter(pk=project.pk).update(guest_view_all_features=True)
        assert names('childOf("WEB-1")', workspace, guest) == ["Polish signup"]

    def test_members_of_hidden_project_is_empty(self, workspace, create_user, other_user, items, secret):
        pql = f'assignee IN membersOf("project:{secret.id}")'
        assert names(pql, workspace, create_user) == []
        # SEC's own member gets its roster (other_user, assigned to WEB-2)
        assert names(pql, workspace, other_user) == ["Polish signup"]

    def test_nesting_depth_is_limited(self, workspace, create_user, items):
        ok = "(" * 10 + 'priority = "urgent"' + ")" * 10
        assert names(ok, workspace, create_user) == ["Fix login capex bug"]
        for deep in ("(" * 11 + 'priority = "urgent"' + ")" * 11, "NOT " * 500 + 'priority = "urgent"'):
            with pytest.raises(PQLError, match="nested too deeply"):
                compile_pql(deep, workspace.slug, create_user)

    def test_too_deep_is_a_400_with_a_pql_key(self, api_key_client, settings, workspace, items):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        response = api_key_client.get(
            f"/api/v1/workspaces/{workspace.slug}/work-items/", {"pql": "(" * 1000 + 'priority = "urgent"' + ")" * 1000}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nested too deeply" in response.json()["pql"]
