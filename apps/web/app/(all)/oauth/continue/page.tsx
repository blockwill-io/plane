/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// BlockWill fork — OAuth sign-in hand-off. The API's /auth/o/authorize-app/
// sends a signed-out browser here; AuthenticationWrapper runs the normal
// Plane login (with next_path back to this page), and once there is a user
// this page returns the browser to the API's consent screen. The hop exists
// because the web app follows next_path with client-side routing, which cannot
// reach an API URL.

import { useEffect } from "react";
import { observer } from "mobx-react";
import { API_BASE_URL } from "@plane/constants";
import { LogoSpinner } from "@/components/common/logo-spinner";
import { useUser } from "@/hooks/store/user";
import { AuthenticationWrapper } from "@/lib/wrappers/authentication-wrapper";

const ContinueToConsent = observer(function ContinueToConsent() {
  const { data: currentUser } = useUser();

  useEffect(() => {
    if (currentUser?.id) window.location.replace(`${API_BASE_URL}/auth/o/authorize-app/consent/`);
  }, [currentUser?.id]);

  return (
    <div className="grid h-screen w-full place-items-center">
      <LogoSpinner />
    </div>
  );
});

export default function OAuthContinuePage() {
  return (
    <AuthenticationWrapper>
      <ContinueToConsent />
    </AuthenticationWrapper>
  );
}
