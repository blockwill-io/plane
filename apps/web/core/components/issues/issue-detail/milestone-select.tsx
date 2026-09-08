/**
 * BlockWill fork — milestone row for the work item sidebar.
 */

import React, { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { cn } from "@plane/utils";
// components
import { MilestoneDropdown } from "@/components/milestones/dropdown";
// hooks
import { useMilestone } from "@/hooks/store/use-milestone";

type TIssueMilestoneSelect = {
  className?: string;
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
};

export const IssueMilestoneSelect = observer(function IssueMilestoneSelect(props: TIssueMilestoneSelect) {
  const { className = "", workspaceSlug, projectId, issueId, disabled = false } = props;
  // states
  const [isUpdating, setIsUpdating] = useState(false);
  // store hooks
  const { getMilestoneByIssueId, addIssuesToMilestone, removeIssueFromMilestone } = useMilestone();
  // derived values
  const currentMilestone = getMilestoneByIssueId(issueId);

  const handleChange = async (milestoneId: string | null) => {
    if ((currentMilestone?.id ?? null) === milestoneId) return;
    setIsUpdating(true);
    try {
      // A work item belongs to one milestone, so moving means unlinking the old one first.
      if (currentMilestone) {
        await removeIssueFromMilestone(workspaceSlug, projectId, currentMilestone.id, issueId);
      }
      if (milestoneId) {
        await addIssuesToMilestone(workspaceSlug, projectId, milestoneId, [issueId]);
      }
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className={cn("flex h-full items-center gap-1", className)}>
      <MilestoneDropdown
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        value={currentMilestone?.id ?? null}
        onChange={handleChange}
        disabled={disabled || isUpdating}
        className="group w-full"
      />
    </div>
  );
});
