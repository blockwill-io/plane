/**
 * BlockWill fork — "StartupOS" filter (property "agent"). One option per
 * known agent; the value sent to the API is the agent key. Combines with the
 * fork's negation ("is not") for "everything not handed to StartupOS".
 */

// plane imports
import type { TAgentKey, TFilterProperty, TSupportedOperators } from "@plane/types";
import { AGENT_KEYS, AGENT_LABELS, COLLECTION_OPERATOR, EQUALITY_OPERATOR } from "@plane/types";
// local imports
import type { IFilterIconConfig, TCreateFilterConfig, TCreateFilterConfigParams } from "../../../rich-filters";
import { createFilterConfig, createOperatorConfigEntry, getMultiSelectConfig } from "../../../rich-filters";

export type TCreateAgentFilterParams = TCreateFilterConfigParams & IFilterIconConfig<TAgentKey>;

export const getAgentMultiSelectConfig = (params: TCreateAgentFilterParams, singleValueOperator: TSupportedOperators) =>
  getMultiSelectConfig<TAgentKey, TAgentKey, TAgentKey>(
    {
      items: [...AGENT_KEYS],
      getId: (agent) => agent,
      getLabel: (agent) => `Assigned to ${AGENT_LABELS[agent]}`,
      getValue: (agent) => agent,
      getIconData: (agent) => agent,
    },
    {
      singleValueOperator,
      ...params,
    },
    {
      getOptionIcon: params.getOptionIcon,
    }
  );

export const getAgentFilterConfig =
  <P extends TFilterProperty>(key: P): TCreateFilterConfig<P, TCreateAgentFilterParams> =>
  (params: TCreateAgentFilterParams) =>
    createFilterConfig<P>({
      id: key,
      label: "StartupOS",
      ...params,
      icon: params.filterIcon,
      supportedOperatorConfigsMap: new Map([
        createOperatorConfigEntry(COLLECTION_OPERATOR.IN, params, (updatedParams) =>
          getAgentMultiSelectConfig(updatedParams, EQUALITY_OPERATOR.EXACT)
        ),
      ]),
    });
