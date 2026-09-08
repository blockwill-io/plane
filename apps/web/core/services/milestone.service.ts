/**
 * BlockWill fork — milestone service. Talks to the fork's milestone endpoints
 * (see plane/app/urls/milestone.py).
 */

import { API_BASE_URL } from "@plane/constants";
import type { TMilestone, TMilestonePayload } from "@plane/types";
// services
import { APIService } from "@/services/api.service";

export class MilestoneService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getMilestones(workspaceSlug: string, projectId: string): Promise<TMilestone[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/milestones/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createMilestone(workspaceSlug: string, projectId: string, data: TMilestonePayload): Promise<TMilestone> {
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/milestones/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateMilestone(
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    data: TMilestonePayload
  ): Promise<TMilestone> {
    return this.patch(`/api/workspaces/${workspaceSlug}/projects/${projectId}/milestones/${milestoneId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async deleteMilestone(workspaceSlug: string, projectId: string, milestoneId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/projects/${projectId}/milestones/${milestoneId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Link work items to a milestone. */
  async addIssuesToMilestone(
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    issues: string[]
  ): Promise<void> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/milestones/${milestoneId}/milestone-issues/`,
      { issues }
    )
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Unlink a single work item from a milestone. */
  async removeIssueFromMilestone(
    workspaceSlug: string,
    projectId: string,
    milestoneId: string,
    issueId: string
  ): Promise<void> {
    return this.delete(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/milestones/${milestoneId}/milestone-issues/${issueId}/`
    )
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
