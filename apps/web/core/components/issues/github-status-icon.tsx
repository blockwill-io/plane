/**
 * BlockWill fork — per-row GitHub status icon for the list and spreadsheet
 * layouts.
 *
 * The Links column only says "1 link"; whether a ticket has a PR — and how far
 * along it is — took opening the peek view. This renders one small color-coded
 * icon next to the work item name: gray branch = branch pushed, gray dashed =
 * draft PR, green = PR open, purple = merged, red = closed unmerged. Rows with
 * no GitHub link render nothing.
 *
 * Data comes from the fork's github-links summary endpoint, fetched once per
 * project (SWR dedupes across rows) rather than once per row. Colors and state
 * parsing match the sidebar's pull-requests widget.
 */

import { GitBranch, GitMerge, GitPullRequest, GitPullRequestClosed, GitPullRequestDraft } from "lucide-react";
import { useParams } from "next/navigation";
import useSWR from "swr";
// plane imports
import { Tooltip } from "@plane/propel/tooltip";
import { cn } from "@plane/utils";
// services
import type { TGithubLinkState, TProjectGithubLinkSummary } from "@/services/github-link.service";
import { githubLinkService } from "@/services/github-link.service";

const STATE_PRESENTATION: Record<TGithubLinkState, { icon: typeof GitPullRequest; className: string; label: string }> =
  {
    open: { icon: GitPullRequest, className: "text-success-primary", label: "PR open" },
    draft: { icon: GitPullRequestDraft, className: "text-tertiary", label: "Draft PR" },
    merged: { icon: GitMerge, className: "text-accent-primary", label: "PR merged" },
    closed: { icon: GitPullRequestClosed, className: "text-danger-primary", label: "PR closed" },
    branch: { icon: GitBranch, className: "text-tertiary", label: "Branch linked" },
  };

const useProjectGithubLinks = (projectId: string | null | undefined): TProjectGithubLinkSummary | undefined => {
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString();
  const { data } = useSWR(
    slug && projectId ? `PROJECT_GITHUB_LINKS_${slug}_${projectId}` : null,
    slug && projectId ? () => githubLinkService.getProjectSummary(slug, projectId) : null,
    { revalidateIfStale: true, revalidateOnFocus: true, refreshInterval: 5 * 60 * 1000 }
  );
  return data;
};

type Props = {
  issueId: string;
  projectId: string | null | undefined;
  className?: string;
};

export function GithubStatusIcon(props: Props) {
  const { issueId, projectId, className } = props;
  const summary = useProjectGithubLinks(projectId)?.[issueId];
  if (!summary) return null;

  const presentation = STATE_PRESENTATION[summary.state] ?? STATE_PRESENTATION.open;
  const Icon = presentation.icon;
  const others = summary.count > 1 ? ` · +${summary.count - 1} more` : "";
  return (
    <Tooltip tooltipContent={`${presentation.label}${others} — ${summary.title ?? summary.url}`}>
      <span className={cn("grid flex-shrink-0 place-items-center", className)}>
        <Icon className={cn("size-3.5", presentation.className)} strokeWidth={2} />
      </span>
    </Tooltip>
  );
}
