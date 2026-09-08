/**
 * BlockWill fork — project milestones settings page.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { ProjectSettingsMilestoneList } from "@/components/milestones/settings-list";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { MilestonesProjectSettingsHeader } from "./header";

function MilestonesSettingsPage() {
  // router
  const { workspaceSlug, projectId } = useParams();
  // store hooks
  const { currentProjectDetails } = useProject();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();

  const pageTitle = currentProjectDetails?.name ? `${currentProjectDetails?.name} - Milestones` : undefined;

  // derived values
  const canPerformProjectMemberActions = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );

  if (workspaceUserInfo && !canPerformProjectMemberActions) {
    return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;
  }

  return (
    <SettingsContentWrapper header={<MilestonesProjectSettingsHeader />}>
      <PageHead title={pageTitle} />
      {workspaceSlug && projectId && (
        <ProjectSettingsMilestoneList
          workspaceSlug={workspaceSlug.toString()}
          projectId={projectId.toString()}
          isEditable={canPerformProjectMemberActions}
        />
      )}
    </SettingsContentWrapper>
  );
}

export default observer(MilestonesSettingsPage);
