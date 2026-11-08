# BlockWill fork — the "guests see only their own work items" rule, shared by
# the fork's project views (milestones, GitHub link and agent summaries, v1
# milestone work items). Mirrors IssueViewSet.list: a project guest without
# guest_view_all_features is limited to the items they created.

from plane.db.models import ProjectMember
from plane.db.models.project import ROLE


def is_restricted_guest(user, slug, project_id) -> bool:
    return ProjectMember.objects.filter(
        workspace__slug=slug,
        project_id=project_id,
        member=user,
        role=ROLE.GUEST.value,
        is_active=True,
        project__guest_view_all_features=False,
    ).exists()


def guest_scope(queryset, user, slug, project_id, field="created_by"):
    """`queryset` as `user` may see it; `field` is the path to the item's creator."""
    if is_restricted_guest(user, slug, project_id):
        return queryset.filter(**{field: user})
    return queryset
