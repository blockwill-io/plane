/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import type {
  TAllAvailableOperatorsForDisplay,
  TFilterConditionNode,
  TFilterExpression,
  TFilterProperty,
  TFilterValue,
  TSupportedOperators,
} from "@plane/types";
import { FILTER_NODE_TYPE } from "@plane/types";
// local imports
import { getNegatedOperator } from "../../operators/shared";

/**
 * Finds a condition node by ID.
 * Local implementation to avoid a circular import with traversal/core.
 * @param expression - The filter expression to search in
 * @param conditionId - The ID of the condition
 * @returns The condition node, or undefined if not found
 */
const findConditionNodeById = <P extends TFilterProperty>(
  expression: TFilterExpression<P>,
  conditionId: string
): TFilterConditionNode<P, TFilterValue> | undefined => {
  if (expression.type === FILTER_NODE_TYPE.CONDITION) {
    return expression.id === conditionId ? expression : undefined;
  }

  for (const child of expression.children) {
    const found = findConditionNodeById(child, conditionId);
    if (found) return found;
  }
  return undefined;
};

/**
 * Helper function to get the display operator for a condition.
 * This checks the condition's negation flag and applies negation if needed.
 * @param operator - The original operator
 * @param expression - The filter expression
 * @param conditionId - The ID of the condition
 * @returns The display operator (possibly negated)
 */
export const getDisplayOperator = <P extends TFilterProperty>(
  operator: TSupportedOperators,
  expression: TFilterExpression<P>,
  conditionId: string
): TAllAvailableOperatorsForDisplay => {
  const condition = findConditionNodeById(expression, conditionId);
  if (condition?.isNegated) return getNegatedOperator(operator);

  // Otherwise, return the operator as-is
  return operator;
};
