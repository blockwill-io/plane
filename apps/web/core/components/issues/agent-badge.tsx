/**
 * BlockWill fork — per-row "StartupOS" badge for the list, kanban and
 * spreadsheet layouts. Rows handed to StartupOS get a small bot chip next to
 * the name; everything else renders nothing.
 *
 * Reads the agent assignment store, which the sidebar toggle also writes, so
 * the badge flips the moment someone assigns or unassigns. The store is
 * filled once per project via the summary endpoint (SWR dedupes across rows).
 */

import { Bot } from "lucide-react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import useSWR from "swr";
// plane imports
import { Tooltip } from "@plane/propel/tooltip";
import { AGENT_LABELS } from "@plane/types";
import { calculateTimeAgo, cn } from "@plane/utils";
// hooks
import { useAgentAssignment } from "@/hooks/store/use-agent-assignment";

export const useProjectAgentAssignments = (projectId: string | null | undefined) => {
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString();
  const { fetchProjectAssignments } = useAgentAssignment();
  useSWR(
    slug && projectId ? `PROJECT_AGENT_ASSIGNMENTS_${slug}_${projectId}` : null,
    slug && projectId ? () => fetchProjectAssignments(slug, projectId) : null,
    { revalidateIfStale: true, revalidateOnFocus: true, refreshInterval: 2 * 60 * 1000 }
  );
};

type Props = {
  issueId: string;
  projectId: string | null | undefined;
  /** "icon" = just the bot glyph (tight rows); "chip" = glyph + label (cards). */
  variant?: "icon" | "chip";
  className?: string;
};

export const AgentBadge = observer(function AgentBadge(props: Props) {
  const { issueId, projectId, variant = "icon", className } = props;
  useProjectAgentAssignments(projectId);
  const { getAssignment } = useAgentAssignment();
  const assignment = getAssignment(issueId);
  if (!assignment) return null;

  const label = AGENT_LABELS[assignment.agent] ?? assignment.agent_label;
  const who = assignment.assigned_by_display_name ? ` by ${assignment.assigned_by_display_name}` : "";
  const tooltip = `Assigned to ${label}${who} ${calculateTimeAgo(assignment.assigned_at)}`;

  if (variant === "chip") {
    return (
      <Tooltip tooltipContent={tooltip}>
        <span
          className={cn(
            "inline-flex h-5 shrink-0 items-center gap-1 rounded-sm border border-accent-strong/40 bg-accent-subtle px-1.5 text-caption-md-medium text-accent-primary",
            className
          )}
        >
          <Bot className="size-3" strokeWidth={2} aria-hidden="true" />
          {label}
        </span>
      </Tooltip>
    );
  }

  return (
    <Tooltip tooltipContent={tooltip}>
      <span className={cn("grid flex-shrink-0 place-items-center", className)} aria-label={tooltip}>
        <Bot className="size-3.5 text-accent-primary" strokeWidth={2} aria-hidden="true" />
      </span>
    </Tooltip>
  );
});
