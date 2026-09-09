/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * BlockWill fork: the real bulk action bar, replacing CE's "Upgrade to One"
 * banner. Everything below it already existed in CE — the selection layer,
 * IssueService.bulkOperations(), and bulkUpdateProperties() on the stores. Only
 * the bar and the server endpoint were missing.
 *
 * A selection can span projects (the global Views page lists several), and
 * states, assignees and labels are all project-scoped, so those controls only
 * appear when the selection sits in a single project. Priority and dates carry
 * no project meaning, so they stay available either way, and every write is
 * grouped by project and sent as one request per project.
 */

import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Trash2, ArchiveIcon, X } from "lucide-react";
// plane imports
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssuePriorities } from "@plane/types";
import { AlertModalCore } from "@plane/ui";
import { cn, renderFormattedPayloadDate } from "@plane/utils";
// components
import { DateDropdown } from "@/components/dropdowns/date";
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
import { PriorityDropdown } from "@/components/dropdowns/priority";
import { StateDropdown } from "@/components/dropdowns/state/dropdown";
// hooks
import { useIssueStoreType } from "@/hooks/use-issue-layout-store";
import { useIssuesActions } from "@/hooks/use-issues-actions";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useIssues } from "@/hooks/store/use-issues";
import { useMultipleSelectStore } from "@/hooks/store/use-multiple-select-store";
import type { TSelectionHelper } from "@/hooks/use-multiple-select";

type Props = {
  className?: string;
  selectionHelpers: TSelectionHelper;
};

export const IssueBulkOperationsRoot = observer(function IssueBulkOperationsRoot(props: Props) {
  const { className, selectionHelpers } = props;
  // router
  const { workspaceSlug } = useParams();
  // store hooks
  const { isSelectionActive, selectedEntityIds } = useMultipleSelectStore();
  const storeType = useIssueStoreType();
  const { issues } = useIssues(storeType);
  const { issue: issueStore } = useIssueDetail();
  // a bulk edit can make work items stop matching the active filters
  const { refreshIssues } = useIssuesActions(storeType);
  // states
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * Bulk endpoints are per project, and the selection is not, so everything is
   * keyed by the project each work item actually belongs to.
   */
  const issueIdsByProject = useMemo(() => {
    const grouped: Record<string, string[]> = {};
    for (const issueId of selectedEntityIds) {
      const projectId = issueStore.getIssueById(issueId)?.project_id;
      if (!projectId) continue;
      grouped[projectId] = [...(grouped[projectId] ?? []), issueId];
    }
    return grouped;
  }, [selectedEntityIds, issueStore]);

  const projectIds = Object.keys(issueIdsByProject);
  // States, assignees and labels only mean something within one project.
  const singleProjectId = projectIds.length === 1 ? projectIds[0] : undefined;
  const selectedCount = selectedEntityIds.length;

  if (!isSelectionActive || selectionHelpers.isSelectionDisabled) return null;

  const slug = workspaceSlug?.toString();

  const runPerProject = async (
    action: (projectId: string, issueIds: string[]) => Promise<unknown> | undefined,
    successMessage: string
  ) => {
    if (!slug || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await Promise.all(
        Object.entries(issueIdsByProject).map(([projectId, issueIds]) => action(projectId, issueIds))
      );
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Success", message: successMessage });
      selectionHelpers.handleClearSelection();
      // Same reason the single-item edit path revalidates: nothing evaluates
      // filter membership on the client, so ask the server what still belongs.
      void refreshIssues?.();
    } catch (error) {
      // Surface the server's reason where it sent one — bulk archive in
      // particular refuses work items that are not completed or cancelled.
      const message =
        (error as { error?: string; message?: string })?.error ??
        (error as { message?: string })?.message ??
        "Something went wrong. Please try again.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Error", message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdate = (properties: Record<string, unknown>) =>
    runPerProject(
      (projectId, issueIds) =>
        issues.bulkUpdateProperties?.(slug as string, projectId, {
          issue_ids: issueIds,
          properties: properties as never,
        }),
      `${selectedCount} work ${selectedCount === 1 ? "item" : "items"} updated.`
    );

  const handleArchive = () =>
    runPerProject(
      (projectId, issueIds) => issues.archiveBulkIssues?.(slug as string, projectId, issueIds),
      `${selectedCount} work ${selectedCount === 1 ? "item" : "items"} archived.`
    );

  const handleDelete = async () => {
    await runPerProject(
      (projectId, issueIds) => issues.removeBulkIssues?.(slug as string, projectId, issueIds),
      `${selectedCount} work ${selectedCount === 1 ? "item" : "items"} deleted.`
    );
    setIsDeleteModalOpen(false);
  };

  return (
    <>
      <AlertModalCore
        handleClose={() => setIsDeleteModalOpen(false)}
        handleSubmit={handleDelete}
        isSubmitting={isSubmitting}
        isOpen={isDeleteModalOpen}
        title="Delete work items"
        content={
          <>
            {`Are you sure you want to delete ${selectedCount} work ${
              selectedCount === 1 ? "item" : "items"
            }? All of the data related to ${
              selectedCount === 1 ? "it" : "them"
            } will be permanently removed. This action cannot be undone.`}
          </>
        }
      />

      <div className={cn("sticky bottom-0 left-0 z-[6] grid h-20 place-items-center px-3.5", className)}>
        <div className="flex h-14 w-full items-center gap-2 overflow-x-auto rounded-md border-[0.5px] border-accent-strong/50 bg-layer-1 px-3.5 py-4 shadow-md">
          <div className="flex flex-shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={selectionHelpers.handleClearSelection}
              aria-label="Clear selection"
              className="grid place-items-center rounded p-1 text-secondary hover:bg-layer-2-hover"
            >
              <X className="size-4" />
            </button>
            <span className="whitespace-nowrap text-body-sm-medium">
              {selectedCount} selected
            </span>
          </div>

          <div className="mx-1 h-5 w-px flex-shrink-0 bg-subtle-1" />

          <div className="flex flex-shrink-0 items-center gap-2">
            {singleProjectId && (
              <StateDropdown
                projectId={singleProjectId}
                value={undefined}
                onChange={(stateId) => handleUpdate({ state_id: stateId })}
                buttonVariant="border-with-text"
                placeholder="State"
                disabled={isSubmitting}
              />
            )}

            <PriorityDropdown
              value={undefined}
              onChange={(priority: TIssuePriorities) => handleUpdate({ priority })}
              buttonVariant="border-with-text"
              placeholder="Priority"
              disabled={isSubmitting}
            />

            {singleProjectId && (
              <MemberDropdown
                projectId={singleProjectId}
                value={[]}
                onChange={(assigneeIds: string[]) => handleUpdate({ assignee_ids: assigneeIds })}
                multiple
                buttonVariant="border-with-text"
                placeholder="Assignees"
                disabled={isSubmitting}
              />
            )}

            <DateDropdown
              value={null}
              onChange={(date) => handleUpdate({ target_date: date ? renderFormattedPayloadDate(date) : null })}
              buttonVariant="border-with-text"
              placeholder="Due date"
              disabled={isSubmitting}
            />
          </div>

          <div className="ml-auto flex flex-shrink-0 items-center gap-1 pl-2">
            <button
              type="button"
              onClick={handleArchive}
              disabled={isSubmitting}
              title="Archive — only completed or cancelled work items can be archived"
              className="flex items-center gap-1.5 rounded px-2 py-1.5 text-body-xs-medium text-secondary hover:bg-layer-2-hover disabled:opacity-50"
            >
              <ArchiveIcon className="size-3.5" />
              Archive
            </button>
            <button
              type="button"
              onClick={() => setIsDeleteModalOpen(true)}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 rounded px-2 py-1.5 text-body-xs-medium text-danger hover:bg-danger-component-surface-light disabled:opacity-50"
            >
              <Trash2 className="size-3.5" />
              Delete
            </button>
          </div>
        </div>
      </div>
    </>
  );
});
