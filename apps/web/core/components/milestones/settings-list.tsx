/**
 * BlockWill fork — milestone management for project settings.
 *
 * Lists a project's milestones with progress, and supports create / rename /
 * retarget / delete inline.
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { Milestone as MilestoneIcon, Plus, Trash2 } from "lucide-react";
// plane imports
import type { TMilestone } from "@plane/types";
import { Button, Input, Loader } from "@plane/ui";
import { cn, renderFormattedDate } from "@plane/utils";
// hooks
import { useMilestone } from "@/hooks/store/use-milestone";

type TMilestoneRowProps = {
  milestone: TMilestone;
  workspaceSlug: string;
  projectId: string;
  isEditable: boolean;
};

const MilestoneRow = observer(function MilestoneRow(props: TMilestoneRowProps) {
  const { milestone, workspaceSlug, projectId, isEditable } = props;
  const { updateMilestone, deleteMilestone } = useMilestone();
  const [title, setTitle] = useState(milestone.title);
  const [targetDate, setTargetDate] = useState(milestone.target_date ?? "");
  const [isDeleting, setIsDeleting] = useState(false);

  const total = milestone.total_issues ?? 0;
  const completed = milestone.completed_issues ?? 0;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  const commitTitle = async () => {
    const next = title.trim();
    if (!next || next === milestone.title) {
      setTitle(milestone.title);
      return;
    }
    await updateMilestone(workspaceSlug, projectId, milestone.id, { title: next }).catch(() =>
      setTitle(milestone.title)
    );
  };

  const commitTargetDate = async () => {
    const next = targetDate || null;
    if (next === (milestone.target_date ?? null)) return;
    await updateMilestone(workspaceSlug, projectId, milestone.id, { target_date: next }).catch(() =>
      setTargetDate(milestone.target_date ?? "")
    );
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteMilestone(workspaceSlug, projectId, milestone.id);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 border-b border-subtle-1 px-1 py-3 last:border-b-0 md:flex-row md:items-center">
      <div className="flex flex-1 items-center gap-2">
        <MilestoneIcon className="h-4 w-4 flex-shrink-0 text-tertiary" />
        {isEditable ? (
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={commitTitle}
            className="w-full border-none bg-transparent px-1 text-body-sm-medium focus:bg-layer-2"
          />
        ) : (
          <span className="truncate px-1 text-body-sm-medium">{milestone.title}</span>
        )}
      </div>

      {/* progress */}
      <div className="flex w-full items-center gap-2 md:w-56">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-layer-2">
          <div
            className={cn("h-full rounded-full", percent === 100 ? "bg-success" : "bg-primary")}
            style={{ width: `${percent}%` }}
          />
        </div>
        <span className="w-20 flex-shrink-0 text-right text-body-xs-regular text-secondary tabular-nums">
          {completed}/{total} done
        </span>
      </div>

      {/* target date */}
      <div className="w-full md:w-44">
        {isEditable ? (
          <Input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            onBlur={commitTargetDate}
            className="w-full border-none bg-transparent px-1 text-body-xs-regular focus:bg-layer-2"
          />
        ) : (
          <span className="px-1 text-body-xs-regular text-secondary">
            {milestone.target_date ? renderFormattedDate(milestone.target_date) : "No date"}
          </span>
        )}
      </div>

      {isEditable && (
        <button
          type="button"
          onClick={handleDelete}
          disabled={isDeleting}
          aria-label={`Delete milestone ${milestone.title}`}
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded text-tertiary hover:bg-layer-2-hover hover:text-danger disabled:opacity-50"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
});

type TProjectSettingsMilestoneListProps = {
  workspaceSlug: string;
  projectId: string;
  isEditable?: boolean;
};

export const ProjectSettingsMilestoneList = observer(function ProjectSettingsMilestoneList(
  props: TProjectSettingsMilestoneListProps
) {
  const { workspaceSlug, projectId, isEditable = true } = props;
  // store hooks
  const { getProjectMilestones, fetchProjectMilestones, createMilestone } = useMilestone();
  // states
  const [isCreating, setIsCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const newTitleInputRef = useRef<HTMLInputElement>(null);
  // derived values
  const milestones = getProjectMilestones(projectId);

  // Focus the title field when the create row opens (an explicit user action,
  // so moving focus here is expected rather than disorienting).
  useEffect(() => {
    if (isCreating) newTitleInputRef.current?.focus();
  }, [isCreating]);

  useEffect(() => {
    if (workspaceSlug && projectId) {
      fetchProjectMilestones(workspaceSlug, projectId).catch(() => {
        // an empty project is a normal state
      });
    }
  }, [workspaceSlug, projectId, fetchProjectMilestones]);

  const handleCreate = async () => {
    const title = newTitle.trim();
    if (!title) return;
    setIsSubmitting(true);
    try {
      await createMilestone(workspaceSlug, projectId, { title });
      setNewTitle("");
      setIsCreating(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 py-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-body-md-semibold">Milestones</h3>
          <p className="text-body-xs-regular text-secondary">
            Checkpoints within this project. Assign work items to a milestone from the work item sidebar.
          </p>
        </div>
        {isEditable && !isCreating && (
          <Button variant="neutral-primary" size="sm" onClick={() => setIsCreating(true)} prependIcon={<Plus />}>
            Add milestone
          </Button>
        )}
      </div>

      {isCreating && (
        <div className="flex items-center gap-2 rounded border border-subtle-1 p-2">
          <MilestoneIcon className="h-4 w-4 flex-shrink-0 text-tertiary" />
          <Input
            ref={newTitleInputRef}
            value={newTitle}
            placeholder="Milestone title"
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
              if (e.key === "Escape") {
                setIsCreating(false);
                setNewTitle("");
              }
            }}
            className="flex-1"
          />
          <Button variant="primary" size="sm" onClick={handleCreate} loading={isSubmitting} disabled={!newTitle.trim()}>
            Create
          </Button>
          <Button
            variant="neutral-primary"
            size="sm"
            onClick={() => {
              setIsCreating(false);
              setNewTitle("");
            }}
          >
            Cancel
          </Button>
        </div>
      )}

      {milestones === undefined ? (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="40px" />
          <Loader.Item height="40px" />
        </Loader>
      ) : milestones.length === 0 ? (
        <div className="rounded border border-dashed border-subtle-1 px-4 py-8 text-center text-body-sm-regular text-secondary">
          No milestones yet. Add one to start tracking checkpoints in this project.
        </div>
      ) : (
        <div className="flex flex-col">
          {milestones.map((milestone) => (
            <MilestoneRow
              key={milestone.id}
              milestone={milestone}
              workspaceSlug={workspaceSlug}
              projectId={projectId}
              isEditable={isEditable}
            />
          ))}
        </div>
      )}
    </div>
  );
});
