"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, HelpCircle } from "lucide-react";
import { apiGet } from "@/lib/api";
import type { Escalation, RecordRow } from "@/lib/types";
import { buildNameMap } from "@/lib/labels";
import { EscalationCard } from "./EscalationCard";

export function EscalationQueue({
  runId,
  entity,
}: {
  runId: string;
  entity: string;
}) {
  const open = useQuery({
    queryKey: ["escalations", runId, "open"],
    queryFn: () =>
      apiGet<Escalation[]>(`/api/runs/${runId}/escalations?status=open`),
    refetchInterval: 2000,
  });
  const all = useQuery({
    queryKey: ["escalations", runId, "all"],
    queryFn: () =>
      apiGet<Escalation[]>(`/api/runs/${runId}/escalations?status=all`),
    refetchInterval: 5000,
  });
  // shared cache with RecordsTable — lets questions say "Priya Sharma"
  const records = useQuery({
    queryKey: ["records", runId],
    queryFn: () => apiGet<RecordRow[]>(`/api/runs/${runId}/records`),
    refetchInterval: 3000,
  });

  const openList = open.data ?? [];
  const nameMap = buildNameMap(records.data ?? []);
  const nameFor = (key: string) => nameMap[key];

  const resolvedCount = (all.data ?? []).filter(
    (e) => e.status === "resolved" && e.resolved_by !== "agent"
  ).length;

  return (
    <section id="questions" className="mt-8 scroll-mt-6">
      <div className="mb-1 flex items-center gap-2">
        <HelpCircle className="h-5 w-5 text-amber-500" />
        <h2 className="text-xl font-semibold text-neutral-900">
          Questions for you
        </h2>
        {openList.length > 0 && (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
            {openList.length}
          </span>
        )}
      </div>
      <p className="mb-4 text-sm text-neutral-500">
        The agent handled everything it was confident about. These are the few
        cases where it wants your judgement.
        {resolvedCount > 0 && (
          <span className="ml-1 text-neutral-400">
            You&rsquo;ve answered {resolvedCount} so far.
          </span>
        )}
      </p>

      {open.isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          Couldn&rsquo;t load the questions — please check the connection and
          try again.
        </div>
      ) : open.isLoading ? (
        <p className="text-sm text-neutral-400">Loading…</p>
      ) : openList.length === 0 ? (
        <div className="flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-600" />
          <div>
            <p className="text-sm font-medium text-emerald-900">
              Nothing needs your attention.
            </p>
            <p className="text-sm text-emerald-700">
              The agent resolved everything on its own — you&rsquo;re good to
              send.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {openList.map((e) => (
            <EscalationCard
              key={e.id}
              escalation={e}
              runId={runId}
              nameFor={nameFor}
              entity={entity}
            />
          ))}
        </div>
      )}
    </section>
  );
}
