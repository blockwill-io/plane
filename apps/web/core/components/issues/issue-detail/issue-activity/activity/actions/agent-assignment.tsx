/**
 * BlockWill fork — activity line for agent assignment (field
 * "agent_assignment", verb "created" | "deleted"; the value is the agent key).
 */

import { observer } from "mobx-react";
import { Bot } from "lucide-react";
// plane imports
import { AGENT_LABELS } from "@plane/types";
import type { TAgentKey } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent, IssueLink } from "./";

type TIssueAgentAssignmentActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

const labelFor = (agent: string | undefined) => (agent ? (AGENT_LABELS[agent as TAgentKey] ?? agent) : "an agent");

export const IssueAgentAssignmentActivity = observer(function IssueAgentAssignmentActivity(
  props: TIssueAgentAssignmentActivity
) {
  const { activityId, showIssue = false, ends } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);
  if (!activity) return <></>;

  const assigned = activity.verb === "created";
  const agent = labelFor(assigned ? activity.new_value : activity.old_value);

  return (
    <IssueActivityBlockComponent
      icon={<Bot className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {assigned ? "assigned " : "unassigned "}
        {showIssue ? <IssueLink activityId={activityId} /> : "the work item"}
        {assigned ? " to " : " from "}
        <span className="font-medium text-primary">{agent}</span>.
      </>
    </IssueActivityBlockComponent>
  );
});
