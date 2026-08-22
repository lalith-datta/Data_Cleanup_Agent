"use client";

import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { apiGet } from "@/lib/api";
import type { RecordRow } from "@/lib/types";
import { fieldLabel, prettyValue, recordStatus } from "@/lib/labels";
import { Avatar, StatusPill } from "./primitives";

/** Which internal statuses to offer as filters, in a friendly order. */
const FILTER_ORDER = [
  "needs_review",
  "valid",
  "pushed",
  "push_failed",
  "invalid",
  "rolled_back",
  "clean",
];

export function RecordsTable({ runId }: { runId: string }) {
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  const records = useQuery({
    queryKey: ["records", runId],
    queryFn: () => apiGet<RecordRow[]>(`/api/runs/${runId}/records`),
    refetchInterval: 3000,
  });

  const all = records.data ?? [];
  const present = FILTER_ORDER.filter((s) => all.some((r) => r.status === s));
  const rows = all.filter((r) => filter === "all" || r.status === filter);

  return (
    <section className="mt-10">
      <h2 className="text-xl font-semibold text-neutral-900">Employees</h2>
      <p className="mb-4 mt-1 text-sm text-neutral-500">
        Everyone the agent pulled together from your files. Open a row to see
        where each value came from.
      </p>

      <div className="mb-3 flex flex-wrap gap-1.5">
        <FilterChip
          label="Everyone"
          count={all.length}
          active={filter === "all"}
          onClick={() => setFilter("all")}
        />
        {present.map((s) => (
          <FilterChip
            key={s}
            label={recordStatus(s).label}
            count={all.filter((r) => r.status === s).length}
            active={filter === s}
            onClick={() => setFilter(s)}
          />
        ))}
      </div>

      <div className="overflow-hidden rounded-2xl border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left text-xs font-medium text-neutral-500">
            <tr>
              <th className="px-4 py-2.5">Employee</th>
              <th className="hidden px-4 py-2.5 sm:table-cell">Department</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => {
              const name =
                (r.merged_json.full_name as string) || "Unknown employee";
              const st = recordStatus(r.status);
              return (
                <Fragment key={r.id}>
                  <tr className="hover:bg-neutral-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <Avatar name={name} size="sm" />
                        <div className="min-w-0">
                          <div className="font-medium text-neutral-900">
                            {name}
                          </div>
                          <div className="text-xs text-neutral-500">
                            {r.merged_json.email || "no email"}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="hidden px-4 py-3 text-neutral-600 sm:table-cell">
                      {r.merged_json.department || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill label={st.label} tone={st.tone} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        className="text-xs font-medium text-neutral-500 hover:text-neutral-900"
                        onClick={() =>
                          setExpanded(expanded === r.id ? null : r.id)
                        }
                      >
                        {expanded === r.id ? "Hide" : "View details"}
                      </button>
                    </td>
                  </tr>
                  {expanded === r.id && (
                    <tr className="bg-neutral-50/70">
                      <td colSpan={4} className="px-4 py-4">
                        <ProvenanceGrid record={r} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-neutral-400">
            {records.isLoading ? "Loading…" : "No employees to show here yet."}
          </p>
        )}
      </div>
    </section>
  );
}

function FilterChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? "bg-neutral-900 text-white"
          : "border bg-white text-neutral-600 hover:border-neutral-300"
      }`}
    >
      {label} <span className={active ? "text-white/60" : "text-neutral-400"}>{count}</span>
    </button>
  );
}

function ProvenanceGrid({ record }: { record: RecordRow }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-neutral-500">
        Where each value came from
      </p>
      <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {Object.entries(record.merged_json).map(([field, value]) => {
          const ref = record.source_refs_json[field];
          return (
            <div key={field} className="flex items-baseline gap-2 text-sm">
              <span className="w-28 shrink-0 text-xs text-neutral-500">
                {fieldLabel(field)}
              </span>
              <span className="min-w-0 flex-1 truncate text-neutral-900">
                {prettyValue(value)}
              </span>
              {ref && <SourceBadge file={ref.file} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SourceBadge({ file }: { file: string }) {
  if (file === "human") {
    return (
      <span className="shrink-0 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700">
        You set this
      </span>
    );
  }
  const friendly = file.replace(/\.(csv|xlsx?|xls)$/i, "");
  return (
    <span className="shrink-0 rounded-full bg-neutral-200 px-2 py-0.5 text-[10px] font-medium text-neutral-600">
      from {friendly}
    </span>
  );
}
