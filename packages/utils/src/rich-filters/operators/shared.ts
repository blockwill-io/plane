/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TAllAvailableOperatorsForDisplay, TNegationOperator, TSupportedOperators } from "@plane/types";
import { NEGATION_OPERATOR_PREFIX } from "@plane/types";

/**
 * Result type for operator conversion
 */
export type TOperatorForPayload = {
  operator: TSupportedOperators;
  isNegation: boolean;
};

/**
 * Type guard to check if a display operator is a negated variant (e.g. "not_in").
 * @param operator - The operator to check
 * @returns True if the operator is a negation display operator
 */
export const isNegationOperator = (operator: TAllAvailableOperatorsForDisplay): operator is TNegationOperator =>
  operator.startsWith(NEGATION_OPERATOR_PREFIX);

/**
 * Builds the negated display variant of an operator.
 * @param operator - The positive operator
 * @returns The negated display operator
 */
export const getNegatedOperator = <T extends TSupportedOperators>(operator: T): TNegationOperator<T> =>
  `${NEGATION_OPERATOR_PREFIX}${operator}`;

/**
 * Converts a display operator to the format needed for supported by filter expression condition.
 * @param displayOperator - The operator from the UI
 * @returns Object with supported operator and negation flag
 */
export const getOperatorForPayload = (displayOperator: TAllAvailableOperatorsForDisplay): TOperatorForPayload => {
  if (isNegationOperator(displayOperator)) {
    return {
      operator: displayOperator.slice(NEGATION_OPERATOR_PREFIX.length) as TSupportedOperators,
      isNegation: true,
    };
  }

  return {
    operator: displayOperator,
    isNegation: false,
  };
};
