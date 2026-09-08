/**
 * BlockWill fork — milestone types.
 *
 * Milestones are named checkpoints within a project (Linear-style). Work items
 * are linked to a milestone through a join row, and progress is the share of a
 * milestone's work items whose state group is "completed".
 */

export type TMilestone = {
  id: string;
  title: string;
  description: string;
  target_date: string | null;
  sort_order: number;
  project_id: string;
  workspace_id: string;
  /** total work items linked to this milestone (annotated by the API) */
  total_issues: number;
  /** linked work items in a completed state (annotated by the API) */
  completed_issues: number;
  /** ids of the work items linked to this milestone (annotated by the API) */
  issue_ids: string[];
  external_source: string | null;
  external_id: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
};

/** Fields accepted when creating or updating a milestone. */
export type TMilestonePayload = Partial<Pick<TMilestone, "title" | "description" | "target_date" | "sort_order">>;
