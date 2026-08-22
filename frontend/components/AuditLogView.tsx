"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "@/lib/api";
import type { AuditEntry, RecordRow } from "@/lib/types";
import { fieldLabel, prettyValue, withArticle } from "@/lib/labels";
import { cn } from "@/lib/utils";

// Human sentence for each human decision.
const HUMAN_ACTIONS: Record<string, string> = {
  resolved_value_conflict: "You picked the right value",
  resolved_ambiguous_mapping: "You sorted out a column",
  resolved_unmapped_column: "You handled an extra column",
  resolved_ambiguous_date: "You confirmed the date format",
  resolved_validation_failure: "You fixed a value",
  resolved_manager_unresolved: "You set the manager",
};

interface Line {
  text: string;
  detail?: string;
}

function friendlyFile(f: string): string {
  return f.replace(/\.(csv|xlsx?|xls)$/i, "");
}

/** Turn one audit row into a sentence a consultant can read at a glance. */
function describe(e: AuditEntry, personFrom: (t: string) => string): Line {
  const after = e.after_json ?? {};

  // human decisions
  if (e.action in HUMAN_ACTIONS) {
    const value = after.value ?? after.action;
    const isReject = after.action === "reject";
    return {
      text: `${HUMAN_ACTIONS[e.action]} for ${personFrom(e.target_id)}`,
      detail: isReject
        ? "left out"
        : value
          ? `chose “${prettyValue(value)}”`
          : undefined,
    };
  }

  switch (e.action) {
    case "mapped_column": {
      const [file, column] = e.target_id.split(":");
      return {
        text: `Linked “${column}” from ${friendlyFile(file)} to ${fieldLabel(
          after.target
        )}`,
      };
    }
    case "cleaned_value": {
      const entry = Object.entries(e.before_json ?? {})[0];
      const field = entry?.[0];
      const before = entry?.[1];
      const afterVal = field ? e.after_json?.[field] : undefined;
      return {
        text: `Tidied up ${personFrom(e.target_id)}’s ${fieldLabel(field ?? "")}`,
        detail:
          before !== undefined
            ? `${prettyValue(before)} → ${prettyValue(afterVal)}`
            : e.reason,
      };
    }
    case "escalated":
      return { text: `Flagged something for your review` };
    case "auto_closed_escalation":
      return {
        text: "Cleared a question automatically",
        detail: "an earlier answer resolved it",
      };
    case "pushed_record":
      return { text: `Sent ${personFrom(e.target_id)} to the new system` };
    case "push_failed":
      return {
        text: `Couldn’t send ${personFrom(e.target_id)}`,
        detail: e.reason,
      };
    case "rolled_back_record":
      return {
        text: `Removed ${personFrom(e.target_id)} from the new system`,
      };
    default:
      return { text: e.reason || e.action.replace(/_/g, " ") };
  }
}

const HUMAN = "You";
const AGENT = "Agent";

export function AuditLogView({
  runId,
  entity,
}: {
  runId: string;
  entity: string;
}) {
  const [who, setWho] = useState<"all" | "agent" | "human">("all");
  const [open, setOpen] = useState(false);

  const audit = useQuery({
    queryKey: ["audit", runId],
    queryFn: () => apiGet<AuditEntry[]>(`/api/runs/${runId}/audit`),
    refetchInterval: 5000,
  });
  const records = useQuery({
    queryKey: ["records", runId],
    queryFn: () => apiGet<RecordRow[]>(`/api/runs/${runId}/records`),
  });

  const nameByKey = new Map(
    (records.data ?? [])
      .filter((r) => typeof r.merged_json.full_name === "string")
      .map((r) => [r.natural_key, r.merged_json.full_name as string])
  );
  const personFrom = (text: string): string => {
    for (const [key, name] of nameByKey) if (text.includes(key)) return name;
    return withArticle(entity);
  };

  const entries = (audit.data ?? [])
    // hide internal/noise rows: activity narration + the duplicate internal
    // conflict write (covered by "resolved_value_conflict")
    .filter(
      (e) =>
        !e.action.startsWith("activity:") && e.action !== "resolved_conflict"
    )
    .filter((e) => who === "all" || e.actor === who)
    .slice()
    .reverse();

  const humanCount = (audit.data ?? []).filter(
    (e) => e.actor === "human" && e.action !== "resolved_conflict"
  ).length;

  return (
    <section className="mt-10">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-2xl border bg-white px-5 py-4 text-left hover:bg-neutral-50"
      >
        <div>
          <h2 className="text-xl font-semibold text-neutral-900">History</h2>
          <p className="mt-0.5 text-sm text-neutral-500">
            A complete record of every step the agent took and every decision
            you made.
            {humanCount > 0 && (
              <span className="ml-1 text-neutral-400">
                {humanCount} of them were yours.
              </span>
            )}
          </p>
        </div>
        <span className="text-sm font-medium text-neutral-500">
          {open ? "Hide" : "Show"}
        </span>
      </button>

      {open && (
        <div className="mt-3">
          <div className="mb-3 flex gap-1.5">
            {(
              [
                ["all", "Everything"],
                ["agent", "The agent"],
                ["human", "You"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setWho(key)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium",
                  who === key
                    ? "bg-neutral-900 text-white"
                    : "border bg-white text-neutral-600 hover:border-neutral-300"
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="max-h-[28rem] overflow-y-auto rounded-2xl border bg-white">
            {audit.isError ? (
              <p className="px-4 py-8 text-center text-sm text-rose-600">
                Couldn&rsquo;t load the history — please check the connection.
              </p>
            ) : entries.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-neutral-400">
                Nothing here yet.
              </p>
            ) : (
              <ul className="divide-y">
                {entries.map((e) => {
                  const line = describe(e, personFrom);
                  const isHuman = e.actor === "human";
                  const failed = e.action === "push_failed";
                  return (
                    <li
                      key={e.id}
                      className="flex items-start gap-3 px-4 py-3 text-sm"
                    >
                      <span
                        className={cn(
                          "mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold",
                          isHuman
                            ? "bg-blue-100 text-blue-700"
                            : "bg-neutral-100 text-neutral-500"
                        )}
                      >
                        {isHuman ? HUMAN : AGENT}
                      </span>
                      <div className="min-w-0 flex-1">
                        <span
                          className={cn(
                            "text-neutral-800",
                            failed && "text-rose-700"
                          )}
                        >
                          {line.text}
                        </span>
                        {line.detail && (
                          <span className="text-neutral-400"> · {line.detail}</span>
                        )}
                      </div>
                      <span className="shrink-0 text-[10px] text-neutral-400">
                        {new Date(e.ts).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
