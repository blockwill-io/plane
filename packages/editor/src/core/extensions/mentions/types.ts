/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane types
import type { TSearchEntities } from "@plane/types";

export enum EMentionComponentAttributeNames {
  ID = "id",
  ENTITY_IDENTIFIER = "entity_identifier",
  ENTITY_NAME = "entity_name",
  // BlockWill fork: a work item mention stores enough to render and link itself.
  // Every issue endpoint is project-scoped, so the work item's uuid alone cannot
  // be resolved back to a project — and carrying the identifier means a document
  // full of mentions renders instantly instead of firing a request per mention.
  PROJECT_ID = "project_id",
  PROJECT_IDENTIFIER = "project_identifier",
  SEQUENCE_ID = "sequence_id",
}

export type TMentionComponentAttributes = {
  [EMentionComponentAttributeNames.ID]: string | null;
  [EMentionComponentAttributeNames.ENTITY_IDENTIFIER]: string | null;
  [EMentionComponentAttributeNames.ENTITY_NAME]: TSearchEntities | null;
  [EMentionComponentAttributeNames.PROJECT_ID]: string | null;
  [EMentionComponentAttributeNames.PROJECT_IDENTIFIER]: string | null;
  [EMentionComponentAttributeNames.SEQUENCE_ID]: string | null;
};
