/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane types
import type { TSearchEntities } from "@plane/types";

export type TMentionSuggestion = {
  entity_identifier: string;
  entity_name: TSearchEntities;
  icon: React.ReactNode;
  id: string;
  subTitle?: string;
  title: string;
  // BlockWill fork: carried onto the node so a work item mention can render and
  // link itself without a lookup. Absent for every other entity type.
  project_id?: string;
  project_identifier?: string;
  sequence_id?: string;
};

export type TMentionSection = {
  key: string;
  title?: string;
  items: TMentionSuggestion[];
};

export type TCallbackMentionComponentProps = Pick<
  TMentionSuggestion,
  "entity_identifier" | "entity_name" | "project_id" | "project_identifier" | "sequence_id"
>;

export type TMentionHandler = {
  getMentionedEntityDetails?: (entity_identifier: string) => { display_name: string } | undefined;
  renderComponent: (props: TCallbackMentionComponentProps) => React.ReactNode;
  searchCallback?: (query: string) => Promise<TMentionSection[]>;
  /**
   * BlockWill fork: search used by the "#" trigger, which mentions work items
   * rather than people. Separate from searchCallback so "#" stays scoped to
   * work items instead of listing every entity type.
   */
  workItemSearchCallback?: (query: string) => Promise<TMentionSection[]>;
};
