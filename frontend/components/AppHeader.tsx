"use client";

import { useQuery } from "@tanstack/react-query";
import { Workflow } from "lucide-react";
import { apiGet } from "@/lib/api";

/** Top bar for the two-pane workspace — brand on the left, live backend
 *  connection status on the right. */
export function AppHeader() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () =>
      apiGet<{ status: string; db: string; llm: string }>("/health"),
    retry: false,
    refetchInterval: 10000,
  });
  const connected = !!health.data;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-5">
      <div className="flex items-center gap-2.5">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-neutral-900 text-white">
          <Workflow className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-neutral-900">
            Migration Assistant
          </div>
          <div className="text-[11px] text-neutral-500">
            Client data migration, with a human in the loop
          </div>
        </div>
      </div>

      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
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
        {connected
          ? `Connected · ${health.data?.llm === "mock" ? "offline AI" : health.data?.llm}`
          : health.isError
            ? "Backend offline"
            : "Connecting…"}
      </span>
    </header>
  );
}
