/**
 * BlockWill fork — milestone store.
 */

import { set, sortBy } from "lodash-es";
import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// types
import type { TMilestone, TMilestonePayload } from "@plane/types";
// services
import { MilestoneService } from "@/services/milestone.service";
// store
import type { CoreRootStore } from "./root.store";

export interface IMilestoneStore {
  // observables
  milestoneMap: Record<string, TMilestone>;
  fetchedMap: Record<string, boolean>;
  // computed fns
  getProjectMilestones: (projectId: string | undefined | null) => TMilestone[] | undefined;
  getMilestoneById: (milestoneId: string | undefined | null) => TMilestone | undefined;
  getMilestoneByIssueId: (issueId: string | undefined | null) => TMilestone | undefined;
  // fetch
  fetchProjectMilestones: (workspaceSlug: string, projectId: string) => Promise<TMilestone[]>;
  // crud
  createMilestone: (workspaceSlug: string, projectId: string, data: TMilestonePayload) => Promise<TMilestone>;
  updateMilestone: (
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    data: TMilestonePayload
  ) => Promise<TMilestone>;
  deleteMilestone: (workspaceSlug: string, projectId: string, milestoneId: string) => Promise<void>;
  // work item links
  addIssuesToMilestone: (
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    issues: string[]
  ) => Promise<void>;
  removeIssueFromMilestone: (
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    issueId: string
  ) => Promise<void>;
}

export class MilestoneStore implements IMilestoneStore {
  // observables
  milestoneMap: Record<string, TMilestone> = {};
  fetchedMap: Record<string, boolean> = {};
  // root store
  rootStore;
  // services
  milestoneService;

  constructor(_rootStore: CoreRootStore) {
    makeObservable(this, {
      milestoneMap: observable,
      fetchedMap: observable,
      // actions
      fetchProjectMilestones: action,
      createMilestone: action,
      updateMilestone: action,
      deleteMilestone: action,
      addIssuesToMilestone: action,
      removeIssueFromMilestone: action,
    });

    this.rootStore = _rootStore;
    this.milestoneService = new MilestoneService();
  }

  /** Milestones of a project, ordered by sort order then target date. */
  getProjectMilestones = computedFn((projectId: string | undefined | null) => {
    if (!projectId || !this.fetchedMap[projectId]) return undefined;
    return sortBy(
      Object.values(this.milestoneMap).filter((milestone) => milestone.project_id === projectId),
      ["sort_order", "target_date"]
    );
  });

  getMilestoneById = computedFn((milestoneId: string | undefined | null) =>
    milestoneId ? this.milestoneMap[milestoneId] : undefined
  );

  /** The milestone a work item belongs to, if any. */
  getMilestoneByIssueId = computedFn((issueId: string | undefined | null) => {
    if (!issueId) return undefined;
    return Object.values(this.milestoneMap).find((milestone) => milestone.issue_ids?.includes(issueId));
  });

  fetchProjectMilestones = async (workspaceSlug: string, projectId: string) => {
    const response = await this.milestoneService.getMilestones(workspaceSlug, projectId);
    runInAction(() => {
      response.forEach((milestone) => set(this.milestoneMap, [milestone.id], milestone));
      set(this.fetchedMap, projectId, true);
    });
    return response;
  };

  createMilestone = async (workspaceSlug: string, projectId: string, data: TMilestonePayload) => {
    const response = await this.milestoneService.createMilestone(workspaceSlug, projectId, data);
    runInAction(() => {
      set(this.milestoneMap, [response.id], response);
    });
    return response;
  };

  updateMilestone = async (
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    data: TMilestonePayload
  ) => {
    const original = this.milestoneMap[milestoneId];
    try {
      // optimistic — reverted below if the request fails
      runInAction(() => {
        set(this.milestoneMap, [milestoneId], { ...original, ...data });
      });
      return await this.milestoneService.updateMilestone(workspaceSlug, projectId, milestoneId, data);
    } catch (error) {
      runInAction(() => {
        set(this.milestoneMap, [milestoneId], original);
      });
      throw error;
    }
  };

  deleteMilestone = async (workspaceSlug: string, projectId: string, milestoneId: string) => {
    await this.milestoneService.deleteMilestone(workspaceSlug, projectId, milestoneId);
    runInAction(() => {
      delete this.milestoneMap[milestoneId];
    });
  };

  addIssuesToMilestone = async (workspaceSlug: string, projectId: string, milestoneId: string, issues: string[]) => {
    await this.milestoneService.addIssuesToMilestone(workspaceSlug, projectId, milestoneId, issues);
    // counts are annotated server-side; refetch so progress stays truthful
    await this.fetchProjectMilestones(workspaceSlug, projectId);
  };

  removeIssueFromMilestone = async (
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    issueId: string
  ) => {
    await this.milestoneService.removeIssueFromMilestone(workspaceSlug, projectId, milestoneId, issueId);
    await this.fetchProjectMilestones(workspaceSlug, projectId);
  };
}
