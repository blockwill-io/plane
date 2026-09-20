/**
 * BlockWill fork — GitHub link summary service. One request per project for
 * the per-row GitHub status icons (see plane/app/views/github_link.py).
 */

import { API_BASE_URL } from "@plane/constants";
// services
import { APIService } from "@/services/api.service";

export type TGithubLinkState = "open" | "draft" | "merged" | "closed" | "branch";

export type TGithubLinkSummary = {
  state: TGithubLinkState;
  title: string | null;
  url: string;
  count: number;
};

export type TProjectGithubLinkSummary = Record<string, TGithubLinkSummary>;

export class GithubLinkService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getProjectSummary(workspaceSlug: string, projectId: string): Promise<TProjectGithubLinkSummary> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/github-links/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

export const githubLinkService = new GithubLinkService();
