# BlockWill fork — feature flags on the v1 API, in Plane Cloud's shape. The MCP
# server's `workspace get_features` / `project get_features` call these, and CE
# had neither (404).
#
#   GET/PATCH /api/v1/workspaces/<slug>/features/
#       Every workspace feature Cloud lists (initiatives, teams, customers, ...)
#       is a paid-edition module this instance does not have, so all read false
#       and turning one on is refused rather than silently ignored.
#   GET/PATCH /api/v1/workspaces/<slug>/projects/<id>/features/
#       Cycles, modules, views, pages and intake map to the real project
#       toggles; the rest read false and cannot be turned on.

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ProjectBasePermission, WorkSpaceAdminPermission, WorkspaceEntityPermission
from plane.db.models import Project

from .base import BaseAPIView

WORKSPACE_FEATURES = (
    "project_grouping",
    "initiatives",
    "teams",
    "customers",
    "wiki",
    "pi",
    "work_item_types",
    "releases",
)
READ_ONLY_WORKSPACE_FEATURES = ("states_owned_by_workspace",)

# project feature -> Project column
PROJECT_TOGGLES = {
    "cycles": "cycle_view",
    "modules": "module_view",
    "views": "issue_views_view",
    "pages": "page_view",
    "intakes": "intake_view",
}
UNAVAILABLE_PROJECT_FEATURES = (
    "epics",
    "work_item_types",
    "workflows",
    "parallel_cycles",
    "project_updates",
)

UNAVAILABLE = "is not available on this Plane edition"


def _check_payload(data, toggles, unavailable, read_only=()):
    """Validate a PATCH body. Returns (updates, error_message)."""
    if not isinstance(data, dict):
        return None, "Expected a JSON object of feature flags"
    updates = {}
    for name, value in data.items():
        if name in read_only:
            return None, f"{name} is read-only"
        if not isinstance(value, bool):
            return None, f"{name} must be true or false"
        if name in toggles:
            updates[toggles[name]] = value
        elif name in unavailable:
            if value:
                return None, f"{name} {UNAVAILABLE}"
        else:
            known = ", ".join([*toggles, *unavailable])
            return None, f"Unknown feature {name!r}; known: {known}"
    return updates, None


class WorkspaceFeatureAPIEndpoint(BaseAPIView):
    def get_permissions(self):
        if self.request.method == "PATCH":
            return [WorkSpaceAdminPermission()]
        return [WorkspaceEntityPermission()]

    def _body(self):
        return {**{name: False for name in WORKSPACE_FEATURES}, "states_owned_by_workspace": False}

    def get(self, request, slug):
        return Response(self._body())

    def patch(self, request, slug):
        _, error = _check_payload(request.data, {}, WORKSPACE_FEATURES, READ_ONLY_WORKSPACE_FEATURES)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._body())


class ProjectFeatureAPIEndpoint(BaseAPIView):
    permission_classes = [ProjectBasePermission]

    def _body(self, project):
        return {
            **{feature: getattr(project, column) for feature, column in PROJECT_TOGGLES.items()},
            **{name: False for name in UNAVAILABLE_PROJECT_FEATURES},
        }

    def _project(self, slug, project_id):
        return Project.objects.filter(workspace__slug=slug, pk=project_id, archived_at__isnull=True).first()

    def get(self, request, slug, project_id):
        project = self._project(slug, project_id)
        if project is None:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._body(project))

    def patch(self, request, slug, project_id):
        project = self._project(slug, project_id)
        if project is None:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        updates, error = _check_payload(request.data, PROJECT_TOGGLES, UNAVAILABLE_PROJECT_FEATURES)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        if updates:
            for column, value in updates.items():
                setattr(project, column, value)
            project.save(update_fields=[*updates, "updated_at", "updated_by"])
        return Response(self._body(project))
