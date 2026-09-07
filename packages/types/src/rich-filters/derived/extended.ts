/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TFilterValue } from "../expression";
import type { TNegationOperator, TExtendedComparisonOperator } from "../operators";
import type { TCoreSupportedDateFilterOperators, TCoreSupportedSelectFilterOperators } from "./core";

// -------- DATE FILTER OPERATORS --------

/**
 * Union type representing all extended operators that support date filter types.
 * BlockWill fork: the LTE/GTE comparison operators are single-date ("before"/"after").
 */
export type TExtendedSupportedDateFilterOperators<_V extends TFilterValue = TFilterValue> = TExtendedComparisonOperator;

export type TExtendedAllAvailableDateFilterOperatorsForDisplay<V extends TFilterValue = TFilterValue> =
  | TExtendedComparisonOperator
  | TNegationOperator<TCoreSupportedDateFilterOperators<V>>;

// -------- SELECT FILTER OPERATORS --------

/**
 * Union type representing all extended operators that support select filter types.
 */
export type TExtendedSupportedSelectFilterOperators<_V extends TFilterValue = TFilterValue> = never;

export type TExtendedAllAvailableSelectFilterOperatorsForDisplay<V extends TFilterValue = TFilterValue> =
  TNegationOperator<TCoreSupportedSelectFilterOperators<V>>;
