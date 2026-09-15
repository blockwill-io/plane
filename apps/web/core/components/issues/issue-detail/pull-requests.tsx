/**
 * BlockWill fork — linked pull requests in the work item sidebar.
 *
 * The github-bridge already attaches every PR to its work item as a Plane
 * issue link, and re-titles that link as the PR moves (open, draft, merged,
 * closed). Those links were only visible in the Links widget far down the
 * page, so finding the PR for a ticket meant scrolling and reading URLs. This
 * surfaces them in Properties, where people already look, as one click per PR.
 *
 * PRs are recognised by URL rather than by the bridge's title format, so a PR
 * link someone pasted in by hand shows up here too. The status is read from
 * the bridge's title when it is there, and simply omitted when it is not —
 * a hand-pasted link still renders, just without a state icon.
 */

import { useMemo } from "react";
import { observer } from "mobx-react";
import { ExternalLink, GitMerge, GitPullRequest, GitPullRequestClosed, GitPullRequestDraft } from "lucide-react";
// plane imports
import { Tooltip } from "@plane/propel/tooltip";
import { cn } from "@plane/utils";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";

type TPullRequestState = "open" | "draft" | "merged" | "closed";

type TLinkedPullRequest = {
  id: string;
  url: string;
  repo: string;
  number: string;
  state?: TPullRequestState;
  title?: string;
};

const STATE_PRESENTATION: Record<TPullRequestState, { icon: typeof GitPullRequest; className: string }> = {
  open: { icon: GitPullRequest, className: "text-success-primary" },
  draft: { icon: GitPullRequestDraft, className: "text-tertiary" },
  merged: { icon: GitMerge, className: "text-accent-primary" },
  closed: { icon: GitPullRequestClosed, className: "text-danger-primary" },
};

const PULL_REQUEST_URL = /github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/i;
const STATES: TPullRequestState[] = ["open", "draft", "merged", "closed"];

/**
 * The bridge writes "PR repo#12 · merged · Some title". Read the state and the
 * PR title out of that, tolerating anything that does not match.
 */
const parseBridgeTitle = (title: string | undefined) => {
  const parts = (title ?? "").split("·").map((part) => part.trim());
  // The state is always the second segment. Scanning every segment would let a
  // PR actually titled "merged" masquerade as one.
  const state = STATES.find((candidate) => parts[1]?.toLowerCase() === candidate);
  // Re-join the rest: a PR title may itself contain the separator.
  return { state, title: parts.length > 2 ? parts.slice(2).join(" · ") : undefined };
};

export const IssuePullRequests = observer(function IssuePullRequests(props: { issueId: string }) {
  const { issueId } = props;
  const {
    link: { getLinksByIssueId, getLinkById },
  } = useIssueDetail();

  const linkIds = getLinksByIssueId(issueId);

  const pullRequests = useMemo<TLinkedPullRequest[]>(() => {
    const seen = new Set<string>();
    const results: TLinkedPullRequest[] = [];
    for (const linkId of linkIds ?? []) {
      const link = getLinkById(linkId);
      const match = link?.url?.match(PULL_REQUEST_URL);
      if (!link || !match) continue;
      // The same PR can be linked more than once — by magic word and by hand.
      const key = `${match[1]}/${match[2]}#${match[3]}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const parsed = parseBridgeTitle(link.title);
      results.push({
        id: link.id,
        url: link.url,
        repo: match[2],
        number: match[3],
        state: parsed.state,
        title: parsed.title,
      });
    }
    // Group by repo, newest PR first within each — numbers from different
    // repos are unrelated, so comparing them across repos would interleave.
    return results.sort((a, b) => a.repo.localeCompare(b.repo) || Number(b.number) - Number(a.number));
  }, [linkIds, getLinkById]);

  if (pullRequests.length === 0) return null;

  return (
    <>
      {pullRequests.map((pullRequest) => {
        const presentation = pullRequest.state ? STATE_PRESENTATION[pullRequest.state] : undefined;
        const Icon = presentation?.icon ?? GitPullRequest;
        return (
          <Tooltip
            key={pullRequest.id}
            tooltipContent={pullRequest.title ?? `${pullRequest.repo}#${pullRequest.number}`}
          >
            <a
              href={pullRequest.url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex h-7.5 max-w-full items-center gap-1.5 rounded px-2 text-body-xs-regular hover:bg-layer-2-hover"
            >
              <Icon className={cn("size-3.5 shrink-0", presentation?.className ?? "text-tertiary")} />
              <span className="truncate font-medium">
                {pullRequest.repo}#{pullRequest.number}
              </span>
              {pullRequest.state && <span className="shrink-0 text-tertiary">{pullRequest.state}</span>}
              <ExternalLink className="size-3 shrink-0 text-tertiary opacity-0 group-hover:opacity-100" />
            </a>
          </Tooltip>
        );
      })}
    </>
  );
});
