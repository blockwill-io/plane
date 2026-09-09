/**
 * BlockWill fork — refresh data when the tab comes back into view.
 *
 * Work item lists and details are fetched once on mount and never revalidated,
 * so anything changed elsewhere (a teammate, or automation closing a ticket on
 * PR merge) shows stale until a manual reload. This re-runs the fetch when the
 * tab regains focus, throttled so quick window switching doesn't hammer the API.
 */

import { useEffect, useRef } from "react";

const DEFAULT_MIN_INTERVAL_MS = 15_000;

export const useRefreshOnFocus = (refresh: () => void, options?: { minIntervalMs?: number; enabled?: boolean }) => {
  const { minIntervalMs = DEFAULT_MIN_INTERVAL_MS, enabled = true } = options ?? {};
  // Keep the latest callback without re-binding listeners on every render.
  const refreshRef = useRef(refresh);
  const lastRefreshedAt = useRef<number>(Date.now());

  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  useEffect(() => {
    if (!enabled || typeof document === "undefined") return;

    const maybeRefresh = () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastRefreshedAt.current < minIntervalMs) return;
      lastRefreshedAt.current = now;
      refreshRef.current();
    };

    document.addEventListener("visibilitychange", maybeRefresh);
    window.addEventListener("focus", maybeRefresh);
    return () => {
      document.removeEventListener("visibilitychange", maybeRefresh);
      window.removeEventListener("focus", maybeRefresh);
    };
  }, [enabled, minIntervalMs]);
};
