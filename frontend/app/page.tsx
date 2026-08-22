"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { apiGet } from "@/lib/api";
import type { Run } from "@/lib/types";
import { runStatus } from "@/lib/labels";
import NewRunForm from "@/components/NewRunForm";
import { StatusPill } from "@/components/primitives";

export default function Home() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () =>
      apiGet<{ status: string; db: string; llm: string }>("/health"),
    retry: false,
  });
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiGet<Run[]>("/api/runs"),
    retry: false,
  });

  const connected = !!health.data;

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <header className="mb-8">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold text-neutral-900">
            Migration Assistant
          </h1>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
              connected
                ? "bg-emerald-100 text-emerald-700"
                : "bg-neutral-100 text-neutral-500"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                connected ? "bg-emerald-500" : "bg-neutral-400"
              }`}
            />
            {connected ? "Connected" : health.isError ? "Offline" : "…"}
          </span>
        </div>
        <p className="mt-1 text-sm text-neutral-500">
          Bring a client&rsquo;s messy employee files into the new system. The
          assistant does the heavy lifting and only checks in with you when it
          genuinely needs a decision.
        </p>
      </header>

      <NewRunForm />

      {runs.data && runs.data.length > 0 && (
        <div className="mt-10">
          <h2 className="mb-2 text-sm font-semibold text-neutral-700">
            Recent migrations
          </h2>
          <ul className="divide-y overflow-hidden rounded-2xl border bg-white">
            {runs.data.map((r) => {
              const st = runStatus(r.status);
              return (
                <li key={r.id}>
                  <a
                    href={`/runs/${r.id}`}
                    className="group flex items-center justify-between gap-3 px-4 py-3.5 hover:bg-neutral-50"
                  >
                    <span className="min-w-0 truncate text-sm font-medium text-neutral-900">
                      {r.name}
                    </span>
                    <span className="flex shrink-0 items-center gap-3">
                      <StatusPill label={st.label} tone={st.tone} />
                      <ArrowRight className="h-4 w-4 text-neutral-300 group-hover:text-neutral-500" />
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </main>
  );
}
