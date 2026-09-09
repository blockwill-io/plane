/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * BlockWill fork: CE ships the entire bulk-operations client — the multi-select
 * layer, IssueService.bulkOperations(), bulkUpdateProperties() on every issue
 * store — and then returns false here, which disables every MultipleSelectGroup
 * and hides the checkboxes outright. Returning true switches the machinery back
 * on; the missing server endpoint it called is implemented in this fork at
 * bulk-operation-issues/.
 *
 * Per-action permissions are still enforced: the layouts pass their own
 * canEditProperties/disableUserActions checks, and the endpoint requires
 * ADMIN or MEMBER.
 */
export const useBulkOperationStatus = () => true;
