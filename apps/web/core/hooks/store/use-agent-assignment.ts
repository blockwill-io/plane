/**
 * BlockWill fork — agent assignment store hook.
 */

import { useContext } from "react";
// mobx store
import { StoreContext } from "@/lib/store-context";
// types
import type { IAgentAssignmentStore } from "@/store/agent-assignment.store";

export const useAgentAssignment = (): IAgentAssignmentStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useAgentAssignment must be used within StoreProvider");
  return context.agentAssignment;
};
