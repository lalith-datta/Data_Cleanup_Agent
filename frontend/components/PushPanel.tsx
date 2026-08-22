"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Send, Undo2 } from "lucide-react";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import type { Run } from "@/lib/types";

interface PushSummary {
  pushed?: number;
  failed?: number;
  retried?: number;
  exhausted?: number;
  still_failed?: number;
  rolled_back?: number;
  run_status?: string;
}

/** Friendly one-line summary of what a send / retry / undo just did. */
function summarize(r: PushSummary): string {
  if (r.rolled_back !== undefined)
    return `Removed ${r.rolled_back} employee${r.rolled_back === 1 ? "" : "s"} from the new system.`;
  if (r.retried !== undefined) {
    const left = r.still_failed ?? 0;
    return left
      ? `Tried again — ${left} still couldn’t be sent.`
      : `Tried again — everything went through this time.`;
  }
  const sent = r.pushed ?? 0;
  const failed = r.failed ?? 0;
  return failed
    ? `Sent ${sent}. ${failed} couldn’t be sent — you can try those again below.`
    : `Sent all ${sent} employees successfully.`;
}

export function PushPanel({ run, runId }: { run: Run; runId: string }) {
  const qc = useQueryClient();
  const [lastResult, setLastResult] = useState<PushSummary | null>(null);
  const [error, setError] = useState("");

  const act = useMutation({
    mutationFn: (path: string) => apiPost<PushSummary>(path),
    onSuccess: (data) => {
      setLastResult(data);
      setError("");
      qc.invalidateQueries({ queryKey: ["run", runId] });
      qc.invalidateQueries({ queryKey: ["records", runId] });
    },
    onError: (e) => setError(e.message),
  });

  const canSend = run.status === "ready_to_push";
  const hasActed = run.status === "completed" || run.status === "pushing";
  const rolledBack = run.status === "rolled_back";

  if (!canSend && !hasActed && !rolledBack) return null;

  const valid = run.stats_json.valid;

  return (
    <section id="send" className="mt-10 scroll-mt-6 rounded-2xl border bg-white p-6">
      <div className="flex items-center gap-2">
        <Send className="h-5 w-5 text-neutral-400" />
        <h2 className="text-xl font-semibold text-neutral-900">
          Send to the new system
        </h2>
      </div>
      <p className="mt-1 text-sm text-neutral-500">
        Adds each ready employee to the client&rsquo;s new platform. If any
        don&rsquo;t go through, you can try them again or undo the whole thing —
        nothing is final until you&rsquo;re happy.
      </p>

      {rolledBack && (
        <p className="mt-3 rounded-xl bg-neutral-50 px-3 py-2 text-sm text-neutral-600">
          Everything that was sent has been removed. Nothing is left in the new
          system.
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {canSend && (
          <button
            type="button"
            disabled={act.isPending}
            onClick={() => act.mutate(`/api/runs/${runId}/push`)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
            Send {valid} employee{valid === 1 ? "" : "s"}
          </button>
        )}
        {hasActed && (
          <>
            {(run.stats_json.push_failed ?? 0) > 0 && (
              <button
                type="button"
                disabled={act.isPending}
                onClick={() => act.mutate(`/api/runs/${runId}/push/retry`)}
                className="inline-flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-neutral-50 disabled:opacity-40"
              >
                <RotateCcw className="h-4 w-4" />
                Try {run.stats_json.push_failed} again
              </button>
            )}
            <button
              type="button"
              disabled={act.isPending}
              onClick={() => act.mutate(`/api/runs/${runId}/rollback`)}
              className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-neutral-500 hover:bg-neutral-100 disabled:opacity-40"
            >
              <Undo2 className="h-4 w-4" />
              Undo everything
            </button>
          </>
        )}
      </div>

      {lastResult && (
        <p className="mt-3 rounded-xl bg-neutral-50 px-3 py-2 text-sm text-neutral-700">
          {summarize(lastResult)}
        </p>
      )}
      {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
    </section>
  );
}
