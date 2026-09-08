/**
 * BlockWill fork — milestone picker.
 *
 * A work item belongs to at most one milestone, so this is a single select
 * with an explicit "No milestone" entry to clear the link.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { Milestone as MilestoneIcon } from "lucide-react";
// plane imports
import { cn, CustomSearchSelect } from "@plane/ui";
// hooks
import { useMilestone } from "@/hooks/store/use-milestone";

export const NO_MILESTONE_VALUE = "none";

type TMilestoneDropdownProps = {
  workspaceSlug: string;
  projectId: string;
  value: string | null;
  onChange: (milestoneId: string | null) => void;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
};

export const MilestoneDropdown = observer(function MilestoneDropdown(props: TMilestoneDropdownProps) {
  const {
    workspaceSlug,
    projectId,
    value,
    onChange,
    disabled = false,
    className = "",
    placeholder = "No milestone",
  } = props;
  // store hooks
  const { getProjectMilestones, getMilestoneById, fetchProjectMilestones } = useMilestone();
  // derived values
  const milestones = getProjectMilestones(projectId);
  const selected = getMilestoneById(value);

  useEffect(() => {
    // milestones are project-scoped and cheap; fetch once per project
    if (workspaceSlug && projectId && milestones === undefined) {
      fetchProjectMilestones(workspaceSlug, projectId).catch(() => {
        // a project without milestones is a normal state, not an error to surface
      });
    }
  }, [workspaceSlug, projectId, milestones, fetchProjectMilestones]);

  const options = [
    { value: NO_MILESTONE_VALUE, query: "no milestone", content: <span className="text-secondary">{placeholder}</span> },
    ...(milestones ?? []).map((milestone) => ({
      value: milestone.id,
      query: milestone.title.toLowerCase(),
      content: (
        <div className="flex items-center gap-2 truncate">
          <MilestoneIcon className="h-3.5 w-3.5 flex-shrink-0" />
          <span className="truncate">{milestone.title}</span>
        </div>
      ),
    })),
  ];

  return (
    <CustomSearchSelect
      value={value ?? NO_MILESTONE_VALUE}
      onChange={(next: string) => onChange(next === NO_MILESTONE_VALUE ? null : next)}
      options={options}
      disabled={disabled}
      className={className}
      maxHeight="lg"
      customButton={
        <div
          className={cn(
            "flex h-full w-full items-center gap-1.5 rounded px-2 py-1 text-body-xs-medium",
            !disabled && "hover:bg-layer-2-hover",
            selected ? "" : "text-placeholder"
          )}
        >
          <MilestoneIcon className="h-3.5 w-3.5 flex-shrink-0" />
          <span className="truncate">{selected?.title ?? placeholder}</span>
        </div>
      }
      customButtonClassName="w-full text-left"
    />
  );
});
