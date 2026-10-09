/**
 * BlockWill fork — "StartupOS" row for the work item sidebar and peek view.
 *
 * Unassigned: one button, "Assign to StartupOS". Assigned: a chip saying so,
 * who did it and when, with an X to take it back. The assignment is separate
 * from the human assignees and from the state: the owner stays the owner,
 * and StartupOS moves the state as it works.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Bot, X } from "lucide-react";
// plane imports
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Tooltip } from "@plane/propel/tooltip";
import { AGENT_LABELS, DEFAULT_AGENT } from "@plane/types";
import { calculateTimeAgo, cn, renderFormattedDate } from "@plane/utils";
// hooks
import { useAgentAssignment } from "@/hooks/store/use-agent-assignment";
import { useMember } from "@/hooks/store/use-member";

type TIssueAgentAssignment = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
  className?: string;
};

const AGENT_LABEL = AGENT_LABELS[DEFAULT_AGENT];

export const IssueAgentAssignment = observer(function IssueAgentAssignment(props: TIssueAgentAssignment) {
  const { workspaceSlug, projectId, issueId, disabled = false, className } = props;
  // states
  const [isUpdating, setIsUpdating] = useState(false);
  // store hooks
  const { getAssignment, fetchIssueAssignment, assign, unassign } = useAgentAssignment();
  const { getUserDetails } = useMember();
  // derived values
  const assignment = getAssignment(issueId);

  useEffect(() => {
    // undefined = never loaded for this work item. A project summary may have
    // filled it already, in which case this is skipped.
    if (assignment === undefined) {
      fetchIssueAssignment(workspaceSlug, projectId, issueId).catch(() => {
        // leave the row in its empty state; the next toggle re-fetches
      });
    }
  }, [assignment, workspaceSlug, projectId, issueId, fetchIssueAssignment]);

  const run = async (operation: () => Promise<unknown>, failure: string) => {
    setIsUpdating(true);
    try {
      await operation();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message: failure });
    } finally {
      setIsUpdating(false);
    }
  };

  const handleAssign = () =>
    run(() => assign(workspaceSlug, projectId, issueId), `Could not assign the work item to ${AGENT_LABEL}.`);
  const handleUnassign = () =>
    run(() => unassign(workspaceSlug, projectId, issueId), `Could not unassign the work item from ${AGENT_LABEL}.`);

  const isLocked = disabled || isUpdating;

  if (!assignment) {
    return (
      <div className={cn("flex h-full items-center", className)}>
        <button
          type="button"
          onClick={handleAssign}
          disabled={isLocked}
          className={cn(
            "group/agent flex h-7.5 w-full items-center gap-1.5 rounded-sm px-2 text-left text-body-xs-regular text-placeholder transition-colors",
            "hover:bg-layer-transparent-hover hover:text-secondary",
            "disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-placeholder"
          )}
          aria-label={`Assign to ${AGENT_LABEL}`}
        >
          <Bot className="size-3.5 shrink-0" aria-hidden="true" />
          <span>{isUpdating ? "Assigning…" : `Assign to ${AGENT_LABEL}`}</span>
        </button>
      </div>
    );
  }

  const assignedBy = assignment.assigned_by ? getUserDetails(assignment.assigned_by) : undefined;
  const assignedByName = assignedBy?.display_name ?? assignment.assigned_by_display_name ?? "someone";
  const tooltip = `Assigned to ${AGENT_LABEL} by ${assignedByName} ${calculateTimeAgo(assignment.assigned_at)} (${renderFormattedDate(assignment.assigned_at)}). ${AGENT_LABEL} will pick this up and move the state as it works; the assignees stay the owners.`;

  return (
    <div className={cn("flex h-full min-w-0 items-center", className)}>
      <Tooltip tooltipContent={tooltip} position="top-start">
        <div
          className={cn(
            // min-w-0 + overflow-hidden keep the chip inside the sidebar column so the
            // unassign button is always on screen; the label truncates instead.
            "flex h-7.5 w-full min-w-0 items-center gap-1.5 overflow-hidden rounded-sm border border-accent-strong/40 bg-accent-subtle pr-1 pl-2 text-body-xs-medium text-accent-primary",
            isLocked && "opacity-70"
          )}
        >
          <Bot className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 truncate">Assigned to {AGENT_LABEL}</span>
          {!disabled && (
            <button
              type="button"
              onClick={handleUnassign}
              disabled={isUpdating}
              className={cn(
                "ml-auto grid size-5 shrink-0 place-items-center rounded-sm text-accent-primary/70 transition-colors",
                "hover:bg-accent-primary/15 hover:text-accent-primary",
                "disabled:cursor-not-allowed"
              )}
              aria-label={`Unassign from ${AGENT_LABEL}`}
              title={`Unassign from ${AGENT_LABEL}`}
            >
              <X className="size-3" aria-hidden="true" />
            </button>
          )}
        </div>
      </Tooltip>
    </div>
  );
});
