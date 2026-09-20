# BlockWill fork — per-project GitHub link summary for the list layouts.
#
# The github-bridge attaches branches and PRs to work items as issue links and
# keeps each link's title current ("PR repo#12 · merged · …", "Branch x · repo").
# The issue-detail sidebar already surfaces those (issue-detail/pull-requests.tsx
# in the web app), but list/spreadsheet rows would need one links request per
# row to show anything. This endpoint collapses that into a single call:
# {issue_id: most significant github link + count} for a whole project.

import re

from rest_framework.response import Response

from plane.app.permissions import ProjectEntityPermission
from plane.db.models import IssueLink

from .base import BaseAPIView

PULL_REQUEST_URL = re.compile(r"github\.com/[^/]+/[^/]+/pull/\d+", re.I)
BRANCH_URL = re.compile(r"github\.com/[^/]+/[^/]+/tree/.+", re.I)
PR_STATES = ("open", "draft", "merged", "closed")
# Active work outranks finished work; a bare branch is the weakest signal.
PRECEDENCE = {"open": 5, "draft": 4, "merged": 3, "closed": 2, "branch": 1}


def _classify(url, title):
    """State of one link, or None when it isn't a GitHub branch/PR link.

    The state lives in the title's second "·" segment (the bridge's format,
    same parse as the web sidebar); a hand-pasted PR link without it counts
    as open — linked-and-in-flight is the safest reading.
    """
    if PULL_REQUEST_URL.search(url or ""):
        parts = [p.strip().lower() for p in (title or "").split("·")]
        if len(parts) > 1 and parts[1] in PR_STATES:
            return parts[1]
        return "open"
    if BRANCH_URL.search(url or ""):
        return "branch"
    return None


class ProjectGithubLinkSummaryEndpoint(BaseAPIView):
    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id):
        summary = {}
        links = IssueLink.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            url__icontains="github.com",
        ).values_list("issue_id", "url", "title")
        for issue_id, url, title in links:
            state = _classify(url, title)
            if state is None:
                continue
            issue_id = str(issue_id)
            entry = summary.get(issue_id)
            if entry is None:
                summary[issue_id] = {"state": state, "title": title, "url": url, "count": 1}
            else:
                entry["count"] += 1
                if PRECEDENCE[state] > PRECEDENCE[entry["state"]]:
                    entry.update(state=state, title=title, url=url)
        return Response(summary)
