/**
 * BlockWill fork — agent assignment ("Assign to StartupOS").
 *
 * A work item keeps its human owner (assignees) and its state. Separately it
 * can be handed to an automated agent, which picks it up through the Plane
 * MCP server. The hand-off is a row in the agent-assignments table: present
 * means "assigned to <agent>", absent means "not assigned". It is neither a
 * state nor a label on purpose: the agent moves the state as it works, and
 * labels are per-project and renameable so an agent could never trust one.
 */

/** Known agent keys. Mirrors AGENTS in plane/db/models/agent_assignment.py. */
export const AGENT_KEYS = ["startupos"] as const;
export type TAgentKey = (typeof AGENT_KEYS)[number];

export const AGENT_LABELS: Record<TAgentKey, string> = {
  startupos: "StartupOS",
};

export const DEFAULT_AGENT: TAgentKey = "startupos";

export type TAgentAssignment = {
  id: string;
  issue_id: string;
  agent: TAgentKey;
  agent_label: string;
  assigned_by: string | null;
  assigned_by_display_name: string | null;
  assigned_at: string;
};

/** {issue_id: assignment} for a whole project, from the summary endpoint. */
export type TProjectAgentAssignments = Record<string, TAgentAssignment>;
