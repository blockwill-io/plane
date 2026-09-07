/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TFilterValue } from "../expression";
import type { TDateFilterFieldConfig } from "../field-types";
import type { EXTENDED_COMPARISON_OPERATOR } from "../operators";

// ----------------------------- EXACT Operator -----------------------------
export type TExtendedExactOperatorConfigs = never;

// ----------------------------- IN Operator -----------------------------
export type TExtendedInOperatorConfigs = never;

// ----------------------------- RANGE Operator -----------------------------
export type TExtendedRangeOperatorConfigs = never;

// ----------------------------- LTE / GTE Operators -----------------------------
// BlockWill fork: single-date "is before" / "is after" comparisons.
export type TExtendedLteOperatorConfigs = TDateFilterFieldConfig<TFilterValue>;
export type TExtendedGteOperatorConfigs = TDateFilterFieldConfig<TFilterValue>;

// ----------------------------- Extended Operator Specific Configs -----------------------------
export type TExtendedOperatorSpecificConfigs = {
  [EXTENDED_COMPARISON_OPERATOR.LTE]: TExtendedLteOperatorConfigs;
  [EXTENDED_COMPARISON_OPERATOR.GTE]: TExtendedGteOperatorConfigs;
};
