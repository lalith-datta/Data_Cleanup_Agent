"use client";

import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Six phases a consultant actually cares about, mapped from the internal
 * pipeline states. Reads as a friendly progress line, not an engineering
 * pipeline.
 */
const PHASES = [
  { key: "read", label: "Read files", from: ["created", "ingesting"] },
  { key: "understand", label: "Understand columns", from: ["mapping"] },
  { key: "match", label: "Match people", from: ["reconciling"] },
  { key: "clean", label: "Clean & check", from: ["cleaning", "validating"] },
  { key: "review", label: "Your review", from: ["awaiting_review"] },
  { key: "send", label: "Send", from: ["ready_to_push", "pushing", "completed"] },
];

function phaseIndex(status: string): number {
  const i = PHASES.findIndex((p) => p.from.includes(status));
  if (i !== -1) return i;
  if (status === "completed") return PHASES.length; // all done
  return 0;
}

export function ProgressBanner({ status }: { status: string }) {
  // Terminal, non-linear states get their own honest line rather than being
  // forced onto the happy-path track.
  if (status === "failed" || status === "rolled_back") return null;

  const current = phaseIndex(status);
  const done = status === "completed";

  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
      {PHASES.map((p, i) => {
        const isDone = i < current || done;
        const isActive = i === current && !done;
        return (
          <div key={p.key} className="flex items-center">
            <div
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
                isDone && "bg-emerald-50 text-emerald-700",
                isActive && "bg-blue-600 text-white",
                !isDone && !isActive && "bg-neutral-100 text-neutral-400"
              )}
            >
              {isDone ? (
                <Check className="h-3.5 w-3.5" />
              ) : isActive ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <span className="grid h-3.5 w-3.5 place-items-center text-[9px]">
                  {i + 1}
                </span>
              )}
              {p.label}
            </div>
            {i < PHASES.length - 1 && (
              <span
                className={cn(
                  "mx-1 h-px w-4",
                  i < current ? "bg-emerald-300" : "bg-neutral-200"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
