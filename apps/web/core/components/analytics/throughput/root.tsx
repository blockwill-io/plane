/**
 * BlockWill fork — team throughput report.
 *
 * "How much did we finish, and who finished it?" over a chosen window.
 * Aggregated headline + per-person breakdown, each expandable into the actual
 * work items, which link straight to the ticket.
 */

import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
// plane imports
import type { TThroughputAssigneeBucket } from "@plane/types";
import { Loader } from "@plane/ui";
import { cn, renderFormattedDate } from "@plane/utils";
// components
import AnalyticsWrapper from "../analytics-wrapper";
// hooks
import { useAnalytics } from "@/hooks/store/use-analytics";
// services
import { AnalyticsService } from "@/services/analytics.service";

const analyticsService = new AnalyticsService();

type TRangePreset = {
  key: string;
  label: string;
  /** days back from today; null means a custom range */
  days: number | null;
};

const RANGE_PRESETS: TRangePreset[] = [
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "14d", label: "Last 14 days", days: 14 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "90d", label: "Last 3 months", days: 90 },
  { key: "180d", label: "Last 6 months", days: 180 },
  { key: "365d", label: "Last year", days: 365 },
  { key: "custom", label: "Custom range", days: null },
];

/** yyyy-mm-dd for the API, computed n days back from today. */
const daysAgo = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split("T")[0];
};
const today = () => new Date().toISOString().split("T")[0];

const AssigneeRow = observer(function AssigneeRow(props: {
  bucket: TThroughputAssigneeBucket;
  workspaceSlug: string;
  maxCount: number;
}) {
  const { bucket, workspaceSlug, maxCount } = props;
  const [isOpen, setIsOpen] = useState(false);
  const share = maxCount > 0 ? Math.round((bucket.count / maxCount) * 100) : 0;

  return (
    <div className="border-b border-subtle-1 last:border-b-0">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-3 px-1 py-3 text-left hover:bg-layer-2-hover"
      >
        {isOpen ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-tertiary" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-tertiary" />
        )}
        <span className="flex-1 truncate text-body-sm-medium">{bucket.display_name}</span>
        <div className="hidden h-1.5 w-40 overflow-hidden rounded-full bg-layer-2 md:block">
          <div className="h-full rounded-full bg-primary" style={{ width: `${share}%` }} />
        </div>
        <span className="w-24 flex-shrink-0 text-right text-body-sm-semibold tabular-nums">
          {bucket.count} done
        </span>
      </button>

      {isOpen && (
        <ul className="flex flex-col gap-1 pb-3 pl-8 pr-1">
          {bucket.work_items.map((item) => (
            <li key={`${bucket.assignee_id}-${item.id}`}>
              <Link
                href={`/${workspaceSlug}/projects/${item.project_id}/issues/${item.id}`}
                className="group flex items-center gap-2 rounded px-2 py-1.5 hover:bg-layer-2-hover"
              >
                <span className="flex-shrink-0 font-mono text-body-xs-regular text-tertiary">{item.identifier}</span>
                <span className="flex-1 truncate text-body-xs-regular">{item.name}</span>
                <span className="flex-shrink-0 text-body-xs-regular text-tertiary">
                  {renderFormattedDate(item.completed_at)}
                </span>
                <ExternalLink className="h-3 w-3 flex-shrink-0 text-tertiary opacity-0 group-hover:opacity-100" />
              </Link>
            </li>
          ))}
          {bucket.work_items.length === 0 && (
            <li className="px-2 py-1.5 text-body-xs-regular text-secondary">No work items to show.</li>
          )}
        </ul>
      )}
    </div>
  );
});

const Throughput = observer(function Throughput() {
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString() ?? "";
  // the project picker in the analytics header is shared across tabs
  const { selectedProjects } = useAnalytics();
  const projectIds = selectedProjects?.length ? selectedProjects.join(",") : undefined;
  // states
  const [rangeKey, setRangeKey] = useState<string>("7d");
  const [customStart, setCustomStart] = useState<string>(daysAgo(30));
  const [customEnd, setCustomEnd] = useState<string>(today());

  const preset = RANGE_PRESETS.find((r) => r.key === rangeKey) ?? RANGE_PRESETS[0];
  const isCustom = preset.days === null;

  const { start_date, end_date } = useMemo(
    () =>
      isCustom
        ? { start_date: customStart, end_date: customEnd }
        : { start_date: daysAgo(preset.days as number), end_date: today() },
    [isCustom, customStart, customEnd, preset.days]
  );

  const { data, isLoading, error } = useSWR(
    slug ? `throughput-${slug}-${start_date}-${end_date}-${projectIds ?? "all"}` : null,
    slug
      ? async () => {
          try {
            return await analyticsService.getThroughput(slug, {
              start_date,
              end_date,
              ...(projectIds ? { project_ids: projectIds } : {}),
            });
          } catch (err) {
            // Surface the reason rather than letting the UI fall back to "0",
            // which reads as "nothing was completed" and hides the failure.
            console.error("Throughput request failed", err);
            throw err;
          }
        }
      : null
  );

  const maxCount = useMemo(
    () => (data?.by_assignee ?? []).reduce((max, b) => Math.max(max, b.count), 0),
    [data]
  );

  return (
    <AnalyticsWrapper i18nTitle="common.analytics">
      <div className="flex flex-col gap-6">
        {/* controls */}
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="throughput-range" className="text-body-xs-medium text-secondary">
              Time range
            </label>
            <select
              id="throughput-range"
              value={rangeKey}
              onChange={(e) => setRangeKey(e.target.value)}
              className="h-8 rounded border border-subtle-1 bg-layer-1 px-2 text-body-sm-regular"
            >
              {RANGE_PRESETS.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          {isCustom && (
            <>
              <div className="flex flex-col gap-1">
                <label htmlFor="throughput-from" className="text-body-xs-medium text-secondary">
                  From
                </label>
                <input
                  id="throughput-from"
                  type="date"
                  value={customStart}
                  max={customEnd}
                  onChange={(e) => setCustomStart(e.target.value)}
                  className="h-8 rounded border border-subtle-1 bg-layer-1 px-2 text-body-sm-regular"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="throughput-to" className="text-body-xs-medium text-secondary">
                  To
                </label>
                <input
                  id="throughput-to"
                  type="date"
                  value={customEnd}
                  min={customStart}
                  onChange={(e) => setCustomEnd(e.target.value)}
                  className="h-8 rounded border border-subtle-1 bg-layer-1 px-2 text-body-sm-regular"
                />
              </div>
            </>
          )}
        </div>

        {error ? (
          <div className="rounded-lg border border-subtle-1 bg-layer-1 px-6 py-8 text-center">
            <p className="text-body-sm-medium">Couldn&apos;t load throughput data.</p>
            <p className="mt-1 text-body-xs-regular text-secondary">
              The report didn&apos;t load, so this isn&apos;t a count of zero. Try reloading; if it keeps happening
              the browser console has the reason.
            </p>
          </div>
        ) : isLoading ? (
          <Loader className="flex flex-col gap-3">
            <Loader.Item height="90px" />
            <Loader.Item height="44px" />
            <Loader.Item height="44px" />
          </Loader>
        ) : (
          <>
            {/* headline */}
            <div className="rounded-lg border border-subtle-1 bg-layer-1 px-6 py-5">
              <div className="text-body-xs-medium uppercase tracking-wide text-secondary">Work items completed</div>
              <div className="mt-1 flex items-baseline gap-3">
                <span className="text-4xl font-semibold tabular-nums">{data?.total_completed ?? 0}</span>
                <span className="text-body-sm-regular text-secondary">
                  {renderFormattedDate(start_date)} – {renderFormattedDate(end_date)}
                </span>
              </div>
              {data?.is_truncated && (
                <p className="mt-2 text-body-xs-regular text-secondary">
                  The count is exact; the per-person lists below show the most recent items only.
                </p>
              )}
            </div>

            {/* per person */}
            <div className="rounded-lg border border-subtle-1 bg-layer-1 px-4 py-2">
              <div className="flex items-center justify-between px-1 py-2">
                <h3 className="text-body-sm-semibold">By person</h3>
                <span className="text-body-xs-regular text-secondary">Click a name to see their work items</span>
              </div>
              {(data?.by_assignee ?? []).length === 0 ? (
                <div className="px-1 py-8 text-center text-body-sm-regular text-secondary">
                  No work items were completed in this period.
                </div>
              ) : (
                <div className={cn("flex flex-col")}>
                  {(data?.by_assignee ?? []).map((bucket) => (
                    <AssigneeRow
                      key={bucket.assignee_id ?? "unassigned"}
                      bucket={bucket}
                      workspaceSlug={slug}
                      maxCount={maxCount}
                    />
                  ))}
                </div>
              )}
              <p className="px-1 py-2 text-body-xs-regular text-tertiary">
                A work item with several assignees counts for each of them, so the per-person numbers can add up to
                more than the total above.
              </p>
            </div>
          </>
        )}
      </div>
    </AnalyticsWrapper>
  );
});

export { Throughput };
