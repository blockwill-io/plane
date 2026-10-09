/**
 * BlockWill fork — agent assignment service. Talks to the fork's
 * agent-assignment endpoints (see plane/app/urls/agent_assignment.py).
 */

import { API_BASE_URL } from "@plane/constants";
import type { TAgentAssignment, TAgentKey, TProjectAgentAssignments } from "@plane/types";
// services
import { APIService } from "@/services/api.service";

export class AgentAssignmentService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** Every assignment in a project, keyed by work item id. */
  async getProjectAssignments(workspaceSlug: string, projectId: string): Promise<TProjectAgentAssignments> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/agent-assignments/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getIssueAssignment(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    agent: TAgentKey
  ): Promise<TAgentAssignment | null> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/agent-assignment/`, {
      params: { agent },
    })
      .then((response) => response?.data?.assignment ?? null)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async assign(workspaceSlug: string, projectId: string, issueId: string, agent: TAgentKey): Promise<TAgentAssignment> {
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/agent-assignment/`, {
      agent,
    })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async unassign(workspaceSlug: string, projectId: string, issueId: string, agent: TAgentKey): Promise<void> {
    return this.delete(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/agent-assignment/?agent=${agent}`
    )
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
