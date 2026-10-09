/**
 * BlockWill fork — agent assignment store.
 *
 * One map, issue id -> assignment (or null once we know there is none), fed by
 * the per-project summary endpoint for list views and by the per-issue
 * endpoint for the detail view. The sidebar toggle writes the same map, so a
 * list badge flips the moment the sidebar does.
 */

import { set } from "lodash-es";
import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// types
import type { TAgentAssignment, TAgentKey } from "@plane/types";
import { DEFAULT_AGENT } from "@plane/types";
// services
import { AgentAssignmentService } from "@/services/agent-assignment.service";
// store
import type { CoreRootStore } from "./root.store";

export interface IAgentAssignmentStore {
  // observables
  assignmentMap: Record<string, TAgentAssignment | null>;
  projectFetchedMap: Record<string, boolean>;
  // computed fns
  getAssignment: (issueId: string | undefined | null) => TAgentAssignment | null | undefined;
  isAssigned: (issueId: string | undefined | null) => boolean;
  // fetch
  fetchProjectAssignments: (workspaceSlug: string, projectId: string) => Promise<void>;
  fetchIssueAssignment: (workspaceSlug: string, projectId: string, issueId: string) => Promise<void>;
  // mutate
  assign: (workspaceSlug: string, projectId: string, issueId: string, agent?: TAgentKey) => Promise<TAgentAssignment>;
  unassign: (workspaceSlug: string, projectId: string, issueId: string, agent?: TAgentKey) => Promise<void>;
}

export class AgentAssignmentStore implements IAgentAssignmentStore {
  // observables
  assignmentMap: Record<string, TAgentAssignment | null> = {};
  projectFetchedMap: Record<string, boolean> = {};
  // root store
  rootStore;
  // services
  service;

  constructor(_rootStore: CoreRootStore) {
    makeObservable(this, {
      assignmentMap: observable,
      projectFetchedMap: observable,
      fetchProjectAssignments: action,
      fetchIssueAssignment: action,
      assign: action,
      unassign: action,
    });
    this.rootStore = _rootStore;
    this.service = new AgentAssignmentService();
  }

  /** undefined = not loaded yet, null = loaded and not assigned. */
  getAssignment = computedFn((issueId: string | undefined | null) =>
    issueId ? this.assignmentMap[issueId] : undefined
  );

  isAssigned = computedFn((issueId: string | undefined | null) => !!this.getAssignment(issueId));

  fetchProjectAssignments = async (workspaceSlug: string, projectId: string) => {
    const response = await this.service.getProjectAssignments(workspaceSlug, projectId);
    runInAction(() => {
      // Anything in this project we previously knew as assigned and that is no
      // longer in the summary has been unassigned elsewhere; clear it.
      Object.entries(this.assignmentMap).forEach(([issueId, assignment]) => {
        if (assignment && !response[issueId]) {
          const issue = this.rootStore.issue.issues.getIssueById(issueId);
          if (issue?.project_id === projectId) set(this.assignmentMap, [issueId], null);
        }
      });
      Object.entries(response).forEach(([issueId, assignment]) => set(this.assignmentMap, [issueId], assignment));
      set(this.projectFetchedMap, projectId, true);
    });
  };

  fetchIssueAssignment = async (workspaceSlug: string, projectId: string, issueId: string) => {
    const response = await this.service.getIssueAssignment(workspaceSlug, projectId, issueId, DEFAULT_AGENT);
    runInAction(() => {
      set(this.assignmentMap, [issueId], response);
    });
  };

  /** The activity log gains a line on assign/unassign; pull it in so the
   * detail view shows it without a reload. */
  private refreshActivity = (workspaceSlug: string, projectId: string, issueId: string) => {
    this.rootStore.issue.issueDetail.activity.fetchActivities(workspaceSlug, projectId, issueId).catch(() => {
      // activity is cosmetic here; the assignment itself already succeeded
    });
  };

  assign = async (workspaceSlug: string, projectId: string, issueId: string, agent: TAgentKey = DEFAULT_AGENT) => {
    const response = await this.service.assign(workspaceSlug, projectId, issueId, agent);
    runInAction(() => {
      set(this.assignmentMap, [issueId], response);
    });
    this.refreshActivity(workspaceSlug, projectId, issueId);
    return response;
  };

  unassign = async (workspaceSlug: string, projectId: string, issueId: string, agent: TAgentKey = DEFAULT_AGENT) => {
    await this.service.unassign(workspaceSlug, projectId, issueId, agent);
    runInAction(() => {
      set(this.assignmentMap, [issueId], null);
    });
    this.refreshActivity(workspaceSlug, projectId, issueId);
  };
}
