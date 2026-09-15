/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * BlockWill fork: CE stubs this out — editorMentionTypes was ["user_mention"]
 * only and updateAdditionalSections returned nothing — so mentioning anything
 * other than a person was switched off, even though the mention node already
 * carries an entity_name and the search endpoint already answers for work
 * items. This restores work item mentions, which is what "#" inserts.
 *
 * Only "issue" is enabled. Projects, cycles, modules and pages are left off
 * deliberately: each needs its own rendering and redirection, and mentioning a
 * work item is the one people actually reach for.
 */

import { useCallback, useMemo } from "react";
// plane editor
import type { TMentionSection, TMentionSuggestion } from "@plane/editor";
// plane ui
import { WorkItemsIcon } from "@plane/propel/icons";
// plane types
import type { TIssueSearchResponse, TSearchEntities, TSearchResponse } from "@plane/types";

export type TUseAdditionalEditorMentionArgs = {
  enableAdvancedMentions: boolean;
};

export type TAdditionalEditorMentionHandlerArgs = {
  response: TSearchResponse;
};

export type TAdditionalEditorMentionHandlerReturnType = {
  sections: TMentionSection[];
};

export type TAdditionalParseEditorContentArgs = {
  id: string;
  entityType: TSearchEntities;
};

export type TAdditionalParseEditorContentReturnType =
  | {
      redirectionPath: string;
      textContent: string;
    }
  | undefined;

/** Turn the search response's work items into a mention section. */
export const buildWorkItemMentionSection = (response: TSearchResponse): TMentionSection[] => {
  const workItems = response?.issue;
  if (!workItems || workItems.length === 0) return [];

  const items: TMentionSuggestion[] = workItems.map((workItem: TIssueSearchResponse) => ({
    icon: <WorkItemsIcon className="size-4 shrink-0 text-tertiary" />,
    id: workItem.id,
    entity_identifier: workItem.id,
    entity_name: "issue",
    title: workItem.name,
    // The identifier is how people refer to a work item out loud, so it is
    // what makes a row recognisable in the dropdown.
    subTitle: `${workItem.project__identifier}-${workItem.sequence_id}`,
    // Carried onto the node so the mention can render and link without a lookup.
    project_id: workItem.project_id ?? undefined,
    project_identifier: workItem.project__identifier,
    sequence_id: String(workItem.sequence_id),
  }));

  return [{ key: "issues", title: "Work items", items }];
};

export const useAdditionalEditorMention = (_args: TUseAdditionalEditorMentionArgs) => {
  const updateAdditionalSections = useCallback(
    (args: TAdditionalEditorMentionHandlerArgs): TAdditionalEditorMentionHandlerReturnType => ({
      sections: buildWorkItemMentionSection(args.response),
    }),
    []
  );

  const parseAdditionalEditorContent = useCallback(
    (_args: TAdditionalParseEditorContentArgs): TAdditionalParseEditorContentReturnType => undefined,
    []
  );

  const editorMentionTypes: TSearchEntities[] = useMemo(() => ["user_mention", "issue"], []);

  return {
    updateAdditionalSections,
    parseAdditionalEditorContent,
    editorMentionTypes,
  };
};
