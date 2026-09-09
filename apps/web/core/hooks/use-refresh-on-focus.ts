/**
 * BlockWill fork — keep work item data fresh without a manual reload.
 *
 * Lists and details are fetched once on mount, so anything changed elsewhere
 * (a teammate, or automation closing a ticket on PR merge) shows stale.
 * `useRefreshOnFocus` refreshes when the tab comes back into view, and
 * `usePollWhileVisible` tops that up with a slow background poll.
 *
 * Both are deliberately conservative: they never run while the tab is hidden,
 * never overlap requests, and never interrupt typing — a refresh that yanks
 * the list while you are mid-edit is worse than slightly stale data.
 */

import { useEffect, useRef } from "react";

const DEFAULT_MIN_INTERVAL_MS = 15_000;
const DEFAULT_POLL_INTERVAL_MS = 60_000;

/** True while the user is typing somewhere, so a refresh would be disruptive. */
const isUserTyping = (): boolean => {
  if (typeof document === "undefined") return false;
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName?.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable === true;
};

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

/**
 * Slow poll while the tab is visible. Skips ticks when the tab is hidden, when
 * a previous refresh is still running, and while the user is typing.
 */
export const usePollWhileVisible = (
  refresh: () => void | Promise<void>,
  options?: { intervalMs?: number; enabled?: boolean }
) => {
  const { intervalMs = DEFAULT_POLL_INTERVAL_MS, enabled = true } = options ?? {};
  const refreshRef = useRef(refresh);
  const inFlight = useRef(false);

  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  useEffect(() => {
    if (!enabled || typeof document === "undefined") return;

    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      if (inFlight.current) return;
      if (isUserTyping()) return;
      inFlight.current = true;
      try {
        await refreshRef.current();
      } catch {
        // A failed background refresh should stay silent; the next tick retries.
      } finally {
        inFlight.current = false;
      }
    };

    const id = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(id);
  }, [enabled, intervalMs]);
};
