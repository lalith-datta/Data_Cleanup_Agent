"use client";

import {
  CheckCircle2,
  HelpCircle,
  Loader2,
  PartyPopper,
  Send,
  Sparkles,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import type { Run } from "@/lib/types";
import { countNoun, pluralize } from "@/lib/labels";

const ACTIVE = new Set([
  "created",
  "ingesting",
  "mapping",
  "reconciling",
  "cleaning",
  "validating",
]);

/**
 * The hero: tells the consultant, in one glance and plain language, what the
 * agent did on its own and what (if anything) it needs from them.
 */
export function AgentSummary({
  run,
  fileCount,
  entity,
}: {
  run: Run;
  fileCount: number;
  entity: string;
}) {
  const s = run.stats_json;
  const autoPct = Math.round((s.stp_rate ?? 0) * 100);
  const filesLabel = `${fileCount || "your"} file${fileCount === 1 ? "" : "s"}`;

  if (ACTIVE.has(run.status)) {
    return (
      <Hero
        icon={<Loader2 className="h-6 w-6 animate-spin text-blue-600" />}
        tint="from-blue-50"
        title="Working through your data…"
        subtitle={`Reading ${filesLabel}, matching ${pluralize(entity)} across them, and cleaning things up. This usually takes just a few seconds.`}
      />
    );
  }

  if (run.status === "awaiting_review") {
    const n = s.escalations_open;
    return (
      <Hero
        icon={<Sparkles className="h-6 w-6 text-amber-600" />}
        tint="from-amber-50"
        title="The agent did most of the work on its own."
        subtitle={`It has ${n} thing${n === 1 ? "" : "s"} it isn't sure about and would like your call on.`}
        tiles={[
          { icon: <CheckCircle2 className="h-4 w-4" />, value: `${autoPct}%`, label: "handled automatically" },
          { icon: <Sparkles className="h-4 w-4" />, value: s.records, label: `${pluralize(entity)} found` },
          { icon: <HelpCircle className="h-4 w-4" />, value: n, label: "questions for you", highlight: true },
        ]}
        cta={{ href: "#questions", label: `Review ${n} question${n === 1 ? "" : "s"}` }}
      />
    );
  }

  if (run.status === "ready_to_push") {
    return (
      <Hero
        icon={<CheckCircle2 className="h-6 w-6 text-emerald-600" />}
        tint="from-emerald-50"
        title="Everything's reviewed and ready."
        subtitle={`${countNoun(s.valid, entity)} ${s.valid === 1 ? "is" : "are"} cleaned, checked, and ready to send to the new system.`}
        cta={{ href: "#send", label: `Send ${countNoun(s.valid, entity)}` }}
      />
    );
  }

  if (run.status === "pushing") {
    return (
      <Hero
        icon={<Send className="h-6 w-6 text-blue-600" />}
        tint="from-blue-50"
        title="Sending to the new system…"
        subtitle={`${s.pushed} sent so far${s.push_failed ? `, ${s.push_failed} need another look` : ""}.`}
      />
    );
  }

  if (run.status === "completed") {
    return (
      <Hero
        icon={<PartyPopper className="h-6 w-6 text-emerald-600" />}
        tint="from-emerald-50"
        title="All done!"
        subtitle={`${countNoun(s.pushed, entity)} ${s.pushed === 1 ? "is" : "are"} now in the new system.${
          s.push_failed ? ` ${s.push_failed} couldn't be sent — see below.` : ""
        }`}
      />
    );
  }

  if (run.status === "failed") {
    return (
      <Hero
        icon={<TriangleAlert className="h-6 w-6 text-rose-600" />}
        tint="from-rose-50"
        title="Something went wrong."
        subtitle="The agent hit a problem before finishing. The history below shows exactly where — you can start a fresh migration when ready."
      />
    );
  }

  if (run.status === "rolled_back") {
    return (
      <Hero
        icon={<Undo2 className="h-6 w-6 text-neutral-500" />}
        tint="from-neutral-50"
        title="Changes undone."
        subtitle="Everything that was sent to the new system has been removed. Nothing is left behind."
      />
    );
  }

  return null;
}

// ------------------------------------------------------------------- pieces
function Hero({
  icon,
  tint,
  title,
  subtitle,
  tiles,
  cta,
}: {
  icon: React.ReactNode;
  tint: string;
  title: string;
  subtitle: string;
  tiles?: { icon: React.ReactNode; value: React.ReactNode; label: string; highlight?: boolean }[];
  cta?: { href: string; label: string };
}) {
  return (
    <div
      className={`rounded-2xl border bg-gradient-to-br ${tint} to-white p-6 shadow-sm`}
    >
      <div className="flex items-start gap-4">
        <div className="rounded-xl bg-white/70 p-2.5 shadow-sm">{icon}</div>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-neutral-900">{title}</h2>
          <p className="mt-1 text-sm text-neutral-600">{subtitle}</p>

          {tiles && (
            <div className="mt-4 grid grid-cols-3 gap-3">
              {tiles.map((t) => (
                <div
                  key={t.label}
                  className={`rounded-xl border bg-white/80 p-3 ${
                    t.highlight ? "border-amber-300" : "border-neutral-200"
                  }`}
                >
                  <div className="flex items-center gap-1.5 text-neutral-400">
                    {t.icon}
                  </div>
                  <div className="mt-1 text-2xl font-semibold text-neutral-900">
                    {t.value}
                  </div>
                  <div className="text-xs text-neutral-500">{t.label}</div>
                </div>
              ))}
            </div>
          )}

          {cta && (
            <a
              href={cta.href}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
            >
              {cta.label}
              <span aria-hidden>↓</span>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
