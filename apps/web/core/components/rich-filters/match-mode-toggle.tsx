/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import type { IFilterInstance } from "@plane/shared-state";
import type { TExternalFilter, TFilterProperty, TLogicalOperator } from "@plane/types";
import { LOGICAL_OPERATOR } from "@plane/types";
import { cn, CustomSearchSelect } from "@plane/ui";

const MATCH_MODE_OPTIONS = [
  { value: LOGICAL_OPERATOR.AND, content: "Match all", query: "match all and" },
  { value: LOGICAL_OPERATOR.OR, content: "Match any", query: "match any or" },
];

const getLabel = (operator: TLogicalOperator) => (operator === LOGICAL_OPERATOR.OR ? "Match any" : "Match all");

export type TMatchModeToggleProps<K extends TFilterProperty, E extends TExternalFilter> = {
  filter: IFilterInstance<K, E>;
  isDisabled?: boolean;
};

/**
 * Global "match all" (AND) / "match any" (OR) toggle for the filter row.
 * Only meaningful with two or more conditions; the row hides it otherwise.
 */
export const MatchModeToggle = observer(function MatchModeToggle<K extends TFilterProperty, E extends TExternalFilter>(
  props: TMatchModeToggleProps<K, E>
) {
  const { filter, isDisabled = false } = props;

  return (
    <CustomSearchSelect
      value={filter.rootLogicalOperator}
      onChange={(operator: TLogicalOperator) => filter.setRootLogicalOperator(operator)}
      options={MATCH_MODE_OPTIONS}
      disabled={isDisabled}
      customButtonClassName="h-full"
      customButton={
        <div
          className={cn(
            "flex h-full items-center rounded border border-subtle-1 px-2 text-13 font-medium text-secondary",
            !isDisabled && "hover:bg-layer-2-hover"
          )}
        >
          {getLabel(filter.rootLogicalOperator)}
        </div>
      }
    />
  );
});
