/**
 * BlockWill fork — a work item mention, inserted with "#".
 *
 * Renders as the identifier people already use out loud (WEB-118) and links
 * straight to the work item. The identifier and project come from the node's
 * own attributes rather than a lookup, so a document full of mentions costs no
 * requests and still renders for work items the store has never loaded.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Link } from "react-router";
// plane imports
import { Tooltip } from "@plane/propel/tooltip";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";

type Props = {
  id: string;
  projectId?: string;
  projectIdentifier?: string;
  sequenceId?: string;
};

export const EditorWorkItemMention = observer(function EditorWorkItemMention(props: Props) {
  const { id, projectId, projectIdentifier, sequenceId } = props;
  // router
  const { workspaceSlug } = useParams();
  // store hooks
  const {
    issue: { getIssueById },
  } = useIssueDetail();

  // The store is only a bonus here: it gives a live title for work items that
  // happen to be loaded, and a fresher identifier if one was renamed.
  const workItem = getIssueById(id);
  const identifier =
    projectIdentifier && sequenceId ? `${projectIdentifier}-${sequenceId}` : (workItem?.sequence_id ?? "");
  const resolvedProjectId = workItem?.project_id ?? projectId;

  // Mentions written before this fork carried the identifier have nothing to
  // show, so fall back to something readable rather than an empty chip.
  const label = identifier || "work item";

  const chip = (
    <span className="not-prose inline rounded-sm bg-layer-1 px-1 py-0.5 font-medium text-accent-primary no-underline">
      {label}
    </span>
  );

  if (!workspaceSlug || !resolvedProjectId) return chip;

  return (
    <Tooltip tooltipContent={workItem?.name ?? label} position="top">
      <span className="not-prose inline">
        <Link
          to={`/${workspaceSlug}/projects/${resolvedProjectId}/issues/${id}`}
          className="not-prose inline rounded-sm bg-layer-1 px-1 py-0.5 font-medium text-accent-primary no-underline hover:bg-layer-2-hover"
        >
          {label}
        </Link>
      </span>
    </Tooltip>
  );
});
