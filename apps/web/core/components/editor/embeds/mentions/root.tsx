/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// local imports
import { EditorUserMention } from "./user";
import { EditorWorkItemMention } from "./work-item";
import type { TCallbackMentionComponentProps } from "@plane/editor";

export function EditorMentionsRoot(props: TCallbackMentionComponentProps) {
  const { entity_identifier, entity_name, project_id, project_identifier, sequence_id } = props;

  switch (entity_name) {
    case "user_mention":
      return <EditorUserMention id={entity_identifier} />;
    // BlockWill fork: work item mentions, inserted with "#"
    case "issue":
      return (
        <EditorWorkItemMention
          id={entity_identifier}
          projectId={project_id}
          projectIdentifier={project_identifier}
          sequenceId={sequence_id}
        />
      );
    default:
      return null;
  }
}
