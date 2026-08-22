"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import type { Escalation } from "@/lib/types";
import {
  escalationCopy,
  fieldLabel,
  prettyDate,
  prettyValue,
} from "@/lib/labels";
import { StatusPill, Avatar } from "./primitives";

/**
 * One question, framed for a non-technical consultant: a plain-language
 * headline about a named employee (never a raw key), the choices laid out
 * clearly, and obvious Approve / Correct / Leave-out actions.
 */
export function EscalationCard({
  escalation,
  runId,
  nameFor,
}: {
  escalation: Escalation;
  runId: string;
  /** resolve a reconciliation key to the employee's real name */
  nameFor: (key: string) => string | undefined;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string>("");
  const [custom, setCustom] = useState("");
  const [error, setError] = useState("");

  const resolve = useMutation({
    mutationFn: (body: { action: string; value: string | null }) =>
      apiPost(`/api/escalations/${escalation.id}/resolve`, {
        ...body,
        resolved_by: "consultant",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["escalations", runId] });
      qc.invalidateQueries({ queryKey: ["run", runId] });
      qc.invalidateQueries({ queryKey: ["records", runId] });
    },
    onError: (e) => setError(e.message),
  });

  const copy = escalationCopy(escalation.type);
  const who = subjectName(escalation, nameFor);
  const hasOptions = escalation.options_json.length > 0;

  // A field/date/column choice must come from the real, known list — never
  // free text (a typo'd field name would be accepted as a real mapping).
  const canCorrect =
    escalation.type === "value_conflict" ||
    escalation.type === "validation_failure" ||
    escalation.type === "manager_unresolved";

  const rejectLabel =
    escalation.type === "validation_failure"
      ? "Skip this employee"
      : escalation.type === "unmapped_column" ||
          escalation.type === "ambiguous_mapping"
        ? "Leave this column out"
        : escalation.type === "manager_unresolved"
          ? "Leave blank"
          : "Skip";

  return (
    <div className="rounded-2xl border bg-white p-5 shadow-sm">
      {/* who + what kind of question */}
      <div className="flex items-center justify-between gap-2">
        {who ? (
          <div className="flex items-center gap-2">
            <Avatar name={who} size="sm" />
            <span className="text-sm font-medium text-neutral-800">{who}</span>
          </div>
        ) : (
          <span className="text-sm font-medium text-neutral-800">
            Your files
          </span>
        )}
        <StatusPill label={copy.label} tone={copy.tone} />
      </div>

      {/* the question, in plain language */}
      <p className="mt-3 text-[15px] font-medium leading-snug text-neutral-900">
        {headline(escalation, who)}
      </p>
      <p className="mt-1 text-xs text-neutral-500">{copy.blurb}</p>

      <Context escalation={escalation} />

      {/* choices */}
      {hasOptions && (
        <div className="mt-3 space-y-1.5">
          {escalation.options_json.map((opt, i) => {
            const val = optionValue(opt);
            const active = selected === val;
            return (
              <label
                key={i}
                className={`flex cursor-pointer items-center gap-2.5 rounded-xl border px-3 py-2.5 text-sm transition-colors ${
                  active
                    ? "border-neutral-800 bg-neutral-50"
                    : "border-neutral-200 hover:border-neutral-300"
                }`}
              >
                <input
                  type="radio"
                  name={`esc-${escalation.id}`}
                  checked={active}
                  onChange={() => setSelected(val)}
                  className="accent-neutral-900"
                />
                <span className="text-neutral-800">
                  {optionLabel(escalation, opt)}
                </span>
              </label>
            );
          })}
        </div>
      )}

      {canCorrect && (
        <input
          className="mt-3 w-full rounded-xl border px-3 py-2 text-sm outline-none focus:border-neutral-400"
          placeholder="…or type the correct value"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
        />
      )}

      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}

      {/* actions */}
      <div className="mt-4 flex flex-wrap gap-2">
        {hasOptions && (
          <button
            type="button"
            disabled={resolve.isPending || !selected}
            onClick={() => resolve.mutate({ action: "approve", value: selected })}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-40"
          >
            Use this
          </button>
        )}
        {canCorrect && custom.trim() && (
          <button
            type="button"
            disabled={resolve.isPending}
            onClick={() => resolve.mutate({ action: "correct", value: custom.trim() })}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40"
          >
            Use my value
          </button>
        )}
        {escalation.type !== "ambiguous_date" && (
          <button
            type="button"
            disabled={resolve.isPending}
            onClick={() => resolve.mutate({ action: "reject", value: null })}
            className="rounded-lg px-4 py-2 text-sm font-medium text-neutral-500 hover:bg-neutral-100 disabled:opacity-40"
          >
            {rejectLabel}
          </button>
        )}
      </div>
    </div>
  );
}

// -------------------------------------------------------------- helpers
/** The employee this question is about, by real name where we can find it. */
function subjectName(
  e: Escalation,
  nameFor: (key: string) => string | undefined
): string | undefined {
  const key = e.context_json.record as string | undefined;
  if (!key) return undefined; // mapping/date questions are about files, not a person
  return nameFor(key) ?? prettyKeyLocal(key);
}

function prettyKeyLocal(key: string): string {
  const [prefix, ...rest] = key.split(":");
  const value = rest.join(":") || prefix;
  return prefix === "id" ? `#${value}` : value;
}

function headline(e: Escalation, who?: string): string {
  const c = e.context_json;
  const person = who ?? "this employee";
  switch (e.type) {
    case "ambiguous_mapping":
      return `Where should the column "${c.source_column}" go?`;
    case "unmapped_column":
      return `The column "${c.source_column}" doesn't match any field. Keep it or leave it out?`;
    case "value_conflict":
      return `Your files show two different ${fieldLabel(c.field).toLowerCase()} values for ${person}. Which is correct?`;
    case "ambiguous_date":
      return `How should ${fieldLabel(c.field).toLowerCase()} dates be read (e.g. ${c.samples?.[0]})?`;
    case "validation_failure":
      return `${person}'s ${fieldLabel(c.field).toLowerCase()} needs a fix.`;
    case "manager_unresolved":
      return `Who is ${person}'s manager "${c.manager_name}"?`;
    default:
      return "Please take a look.";
  }
}

function Context({ escalation: e }: { escalation: Escalation }) {
  const c = e.context_json;
  if (e.type === "validation_failure") {
    return (
      <p className="mt-2 rounded-lg bg-neutral-50 px-3 py-2 text-xs text-neutral-600">
        We found <span className="font-medium">{c.error}</span>. Current value:{" "}
        <span className="font-medium text-neutral-800">
          {prettyValue(c.value)}
        </span>
      </p>
    );
  }
  if (c.samples && Array.isArray(c.samples) && e.type !== "value_conflict") {
    return (
      <p className="mt-2 text-xs text-neutral-500">
        Examples from your files: {c.samples.slice(0, 4).join(", ")}
      </p>
    );
  }
  return null;
}

function optionLabel(e: Escalation, opt: Record<string, any>): string {
  if (e.type === "ambiguous_date")
    return `Read as ${prettyDate(opt.parsed)}`;
  if (e.type === "value_conflict")
    return `${prettyValue(opt.value)}  ·  from ${friendlyFile(opt.source)}`;
  if (e.type === "manager_unresolved")
    return opt.value;
  // mapping questions: options are candidate target fields
  return fieldLabel(String(opt.field ?? opt.value ?? ""));
}

function optionValue(opt: Record<string, any>): string {
  return String(opt.field ?? opt.value ?? opt.format ?? "");
}

function friendlyFile(name?: string): string {
  if (!name) return "a file";
  return name.replace(/\.(csv|xlsx?|xls)$/i, "");
}
