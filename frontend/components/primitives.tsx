"use client";

import { cn } from "@/lib/utils";
import { initials, type Tone } from "@/lib/labels";

// ------------------------------------------------------------------ tone map
const TONE_PILL: Record<Tone, string> = {
  active: "bg-blue-100 text-blue-700",
  attention: "bg-amber-100 text-amber-800",
  success: "bg-emerald-100 text-emerald-800",
  error: "bg-rose-100 text-rose-700",
  neutral: "bg-neutral-100 text-neutral-600",
};

const TONE_DOT: Record<Tone, string> = {
  active: "bg-blue-500",
  attention: "bg-amber-500",
  success: "bg-emerald-500",
  error: "bg-rose-500",
  neutral: "bg-neutral-400",
};

/** A soft, rounded status chip in plain language. */
export function StatusPill({
  label,
  tone,
  className,
}: {
  label: string;
  tone: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONE_PILL[tone],
        className
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", TONE_DOT[tone])} />
      {label}
    </span>
  );
}

export function ToneDot({ tone }: { tone: Tone }) {
  return (
    <span className={cn("inline-block h-2 w-2 rounded-full", TONE_DOT[tone])} />
  );
}

// -------------------------------------------------------------------- avatar
const AVATAR_COLORS = [
  "bg-blue-100 text-blue-700",
  "bg-emerald-100 text-emerald-700",
  "bg-violet-100 text-violet-700",
  "bg-amber-100 text-amber-700",
  "bg-rose-100 text-rose-700",
  "bg-teal-100 text-teal-700",
];

function colorFor(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

/** Initials avatar — gives each employee a friendly, recognisable face. */
export function Avatar({
  name,
  size = "md",
}: {
  name: string;
  size?: "sm" | "md";
}) {
  const dim = size === "sm" ? "h-7 w-7 text-[10px]" : "h-9 w-9 text-xs";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        dim,
        colorFor(name)
      )}
    >
      {initials(name)}
    </span>
  );
}
