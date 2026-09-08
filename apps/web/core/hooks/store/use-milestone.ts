/**
 * BlockWill fork — milestone store hook.
 */

import { useContext } from "react";
// mobx store
import { StoreContext } from "@/lib/store-context";
// types
import type { IMilestoneStore } from "@/store/milestone.store";

export const useMilestone = (): IMilestoneStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useMilestone must be used within StoreProvider");
  return context.milestone;
};
