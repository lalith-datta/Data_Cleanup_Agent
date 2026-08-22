"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FolderClock, Inbox } from "lucide-react";
import { apiGet } from "@/lib/api";
import type { Run } from "@/lib/types";
import { runStatus } from "@/lib/labels";
import { StatusPill } from "@/components/primitives";

/** One-line, plain-language summary of where a run stands. */
function summary(run: Run): string {
  const s = run.stats_json;
  switch (run.status) {
    case "awaiting_review":
      return `${s.escalations_open} question${s.escalations_open === 1 ? "" : "s"} need you`;
    case "ready_to_push":
      return `${s.valid} ready to send`;
    case "pushing":
      return `${s.pushed} sent${s.push_failed ? `, ${s.push_failed} to retry` : "…"}`;
    case "completed":
      return `${s.pushed} sent`;
    case "failed":
      return "Stopped before finishing";
    case "rolled_back":
      return "Changes undone";
    case "created":
      return "Not started yet";
    default:
      return "Working…";
  }
}

export default function MigrationsList() {
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiGet<Run[]>("/api/runs"),
    refetchInterval: 3000,
  });

  const list = runs.data ?? [];

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-1 flex items-center gap-2">
        <FolderClock className="h-5 w-5 text-neutral-400" />
        <h1 className="text-xl font-semibold text-neutral-900">
          Your migrations
        </h1>
      </div>
      <p className="mb-5 text-sm text-neutral-500">
        Pick one to see how it&rsquo;s going, or start a new one from the left.
      </p>

      {runs.isError ? (
        <EmptyCard
          title="Can't reach the backend"
          body="Check that the API is running and try again."
        />
      ) : runs.isLoading ? (
        <p className="text-sm text-neutral-400">Loading…</p>
      ) : list.length === 0 ? (
        <EmptyCard
          title="No migrations yet"
          body="Upload a client's data files on the left to start your first one."
        />
      ) : (
        <ul className="space-y-2">
          {list.map((r) => {
            const st = runStatus(r.status);
            return (
              <li key={r.id}>
                <a
                  href={`/runs/${r.id}`}
                  className="group flex items-center justify-between gap-3 rounded-xl border bg-white px-4 py-3.5 hover:border-neutral-300 hover:shadow-sm"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-neutral-900">
                      {r.name}
                    </div>
                    <div className="mt-0.5 text-xs text-neutral-500">
                      {summary(r)}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <StatusPill label={st.label} tone={st.tone} />
                    <ArrowRight className="h-4 w-4 text-neutral-300 group-hover:text-neutral-500" />
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function EmptyCard({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed bg-white px-6 py-14 text-center">
      <div className="rounded-full bg-neutral-100 p-3">
        <Inbox className="h-6 w-6 text-neutral-400" />
      </div>
      <p className="mt-3 text-sm font-medium text-neutral-800">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-neutral-500">{body}</p>
    </div>
  );
}
