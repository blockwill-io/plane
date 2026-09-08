/**
 * BlockWill fork — milestones settings header.
 */

import { observer } from "mobx-react";
// plane imports
import { PROJECT_SETTINGS } from "@plane/constants";
import { Breadcrumbs } from "@plane/ui";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { SettingsPageHeader } from "@/components/settings/page-header";
import { PROJECT_SETTINGS_ICONS } from "@/components/settings/project/sidebar/item-icon";

export const MilestonesProjectSettingsHeader = observer(function MilestonesProjectSettingsHeader() {
  const settingsDetails = PROJECT_SETTINGS.milestones;
  const Icon = PROJECT_SETTINGS_ICONS.milestones;

  return (
    <SettingsPageHeader
      leftItem={
        <div className="flex items-center gap-2">
          <Breadcrumbs>
            <Breadcrumbs.Item
              component={
                <BreadcrumbLink label={settingsDetails.i18n_label} icon={<Icon className="size-4 text-tertiary" />} />
              }
            />
          </Breadcrumbs>
        </div>
      }
    />
  );
});
