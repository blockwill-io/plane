/**
 * BlockWill fork — "#" mentions a work item, the way "@" mentions a person.
 *
 * This deliberately adds only a second suggestion plugin rather than a second
 * node type: both triggers insert the same `mention` node, so a work item
 * mention is the same thing whether it arrived via "#" or via "@", and every
 * document already in the database keeps rendering unchanged. A second node
 * type would have meant a parallel schema, serializer and node view to keep in
 * step forever.
 */

import { Extension } from "@tiptap/core";
import { PluginKey } from "@tiptap/pm/state";
import Suggestion, { findSuggestionMatch } from "@tiptap/suggestion";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";
// types
import type { TMentionHandler } from "@/types";
// local imports
import { renderMentionsDropdown } from "./utils";

export const WORK_ITEM_MENTION_TRIGGER_KEY = new PluginKey("workItemMentionTrigger");

type Props = Pick<TMentionHandler, "workItemSearchCallback">;

export function WorkItemMentionTriggerExtension(props: Props) {
  const { workItemSearchCallback } = props;

  return Extension.create({
    name: "workItemMentionTrigger",

    addProseMirrorPlugins() {
      if (!workItemSearchCallback) return [];

      return [
        Suggestion({
          editor: this.editor,
          char: "#",
          pluginKey: WORK_ITEM_MENTION_TRIGGER_KEY,
          allowedPrefixes: [" ", "("],
          // A work item's identifier has no spaces, and allowing them here
          // would keep the dropdown open across the rest of the sentence.
          allowSpaces: false,
          // "#" at the start of a line is a markdown heading. allowedPrefixes
          // cannot express this — its check is /^[...]?$/, so an empty prefix
          // always passes — and startOfLine means the opposite of what is
          // wanted here. So reject the match outright when the "#" opens the
          // block, and let the heading input rule have it.
          findSuggestionMatch: (config) => {
            const match = findSuggestionMatch(config);
            if (match && match.range.from === config.$position.start()) return null;
            return match;
          },
          command: ({ editor, range, props: attrs }) => {
            // Mirrors @tiptap/extension-mention's own command: swallow the
            // following space so selecting an item does not leave a double one.
            const nodeAfter = editor.view.state.selection.$to.nodeAfter;
            const overrideSpace = nodeAfter?.text?.startsWith(" ");
            const to = overrideSpace ? range.to + 1 : range.to;

            editor
              .chain()
              .focus()
              .insertContentAt(
                { from: range.from, to },
                [
                  { type: CORE_EXTENSIONS.MENTION, attrs },
                  { type: "text", text: " " },
                ]
              )
              .run();
            window.getSelection()?.collapseToEnd();
          },
          render: renderMentionsDropdown({
            searchCallback: workItemSearchCallback,
          }),
        }),
      ];
    },
  });
}
