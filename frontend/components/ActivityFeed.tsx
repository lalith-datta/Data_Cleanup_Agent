"use client";

import { Activity } from "lucide-react";
import type { ActivityEvent } from "@/lib/types";
import { runStatus } from "@/lib/labels";
import { ToneDot } from "./primitives";

/** A gentle, human narration of what the agent is doing right now. */
export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  const ordered = [...events].reverse(); // newest first

  return (
    <div className="rounded-2xl border bg-white p-5">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="h-4 w-4 text-neutral-400" />
        <h3 className="text-sm font-semibold text-neutral-700">
          What the agent is doing
        </h3>
      </div>
      {ordered.length === 0 ? (
        <p className="text-sm text-neutral-400">Getting started…</p>
      ) : (
        <ul className="space-y-2.5">
          {ordered.map((e) => {
            const failed = e.stage === "failed";
            const { label, tone } = failed
              ? { label: "Problem", tone: "error" as const }
              : runStatus(e.stage);
            return (
              <li key={e.id} className="flex items-start gap-2.5 text-sm">
                <span className="mt-1.5">
                  <ToneDot tone={tone} />
                </span>
                <div className="min-w-0">
                  <span
                    className={
                      failed
                        ? "font-medium text-rose-700"
                        : "font-medium text-neutral-800"
                    }
                  >
                    {label}
                  </span>
                  <span className="text-neutral-500"> — {e.message}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
