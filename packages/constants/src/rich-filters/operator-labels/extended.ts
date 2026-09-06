/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TCoreSupportedDateFilterOperators, TExtendedSupportedOperators, TNegationOperator } from "@plane/types";

/**
 * Extended operator labels
 */
export const EXTENDED_OPERATOR_LABELS_MAP: Record<TExtendedSupportedOperators, string> = {} as const;

/**
 * Extended date-specific operator labels
 */
export const EXTENDED_DATE_OPERATOR_LABELS_MAP: Record<TExtendedSupportedOperators, string> = {} as const;

/**
 * Negated operator labels for all operators
 */
export const NEGATED_OPERATOR_LABELS_MAP: Record<TNegationOperator, string> = {
  not_exact: "is not",
  not_in: "is not any of",
  not_range: "not between",
} as const;

/**
 * Negated date operator labels for all date operators
 */
export const NEGATED_DATE_OPERATOR_LABELS_MAP: Record<TNegationOperator<TCoreSupportedDateFilterOperators>, string> = {
  not_exact: "is not",
  not_range: "not between",
} as const;
