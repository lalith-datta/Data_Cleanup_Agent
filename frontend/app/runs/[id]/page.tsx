"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2 } from "lucide-react";
import { use } from "react";
import { apiGet } from "@/lib/api";
import type { ActivityEvent, Run, SourceFile } from "@/lib/types";
import { runStatus } from "@/lib/labels";
import { ActivityFeed } from "@/components/ActivityFeed";
import { AgentSummary } from "@/components/AgentSummary";
import { AuditLogView } from "@/components/AuditLogView";
import { EscalationQueue } from "@/components/EscalationQueue";
import { ProgressBanner } from "@/components/ProgressBanner";
import { PushPanel } from "@/components/PushPanel";
import { RecordsTable } from "@/components/RecordsTable";
import { StatusPill } from "@/components/primitives";

const ACTIVE_STATUSES = new Set([
  "ingesting",
  "mapping",
  "reconciling",
  "cleaning",
  "validating",
  "pushing",
]);

export default function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const run = useQuery({
    queryKey: ["run", id],
    queryFn: () => apiGet<Run>(`/api/runs/${id}`),
    refetchInterval: 1500,
  });

  const files = useQuery({
    queryKey: ["files", id],
    queryFn: () => apiGet<SourceFile[]>(`/api/runs/${id}/files`),
  });

  const status = run.data?.status ?? "ingesting";
  const isActive = ACTIVE_STATUSES.has(status);
  const showProgress = status !== "failed" && status !== "rolled_back";

  const activity = useQuery({
    queryKey: ["activity", id],
    queryFn: () => apiGet<ActivityEvent[]>(`/api/runs/${id}/activity`),
    refetchInterval: isActive ? 1000 : false,
    enabled: !run.isLoading,
  });

  const st = runStatus(status);
  const escalationsOpen = run.data?.stats_json.escalations_open ?? 0;

  // Show a spinner while the initial data is loading — avoids flashing
  // misleading progress stages (e.g. "analyzing files") for finished runs.
  if (run.isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <a
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-900"
        >
          <ArrowLeft className="h-4 w-4" />
          All migrations
        </a>
        <div className="mt-32 flex flex-col items-center justify-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-neutral-400" />
          <p className="text-sm text-neutral-500">Loading migration…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <a
        href="/"
        className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-900"
      >
        <ArrowLeft className="h-4 w-4" />
        All migrations
      </a>

      <header className="mb-6 mt-3 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-neutral-900">
          {run.data?.name ?? "Loading…"}
        </h1>
        <StatusPill label={st.label} tone={st.tone} />
      </header>

      {run.data && (
        <AgentSummary run={run.data} fileCount={files.data?.length ?? 0} />
      )}

      {showProgress && (
        <div className="mt-4 rounded-2xl border bg-white p-4">
          <ProgressBanner status={status} />
        </div>
      )}

      {/* Watch: live narration while there's motion. */}
      {(isActive || status === "created") && (
        <div className="mt-4">
          <ActivityFeed events={activity.data ?? []} />
        </div>
      )}

      {(status === "awaiting_review" || escalationsOpen > 0) && (
        <EscalationQueue runId={id} />
      )}

      {run.data && <PushPanel run={run.data} runId={id} />}

      <RecordsTable runId={id} />

      <AuditLogView runId={id} />
    </div>
  );
}

