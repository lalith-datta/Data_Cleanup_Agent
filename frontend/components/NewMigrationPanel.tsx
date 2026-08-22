"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Sparkles, UploadCloud, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { apiPost, apiUpload } from "@/lib/api";
import type { Run } from "@/lib/types";

/** Left rail: the persistent "start a migration" panel. Stays mounted while
 *  the right pane switches between the list and a run's detail. */
export function NewMigrationPanel() {
  const router = useRouter();
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  const start = useMutation({
    mutationFn: async () => {
      const run = await apiPost<Run>("/api/runs", { name });
      await apiUpload(`/api/runs/${run.id}/files`, files);
      await apiPost(`/api/runs/${run.id}/start`);
      return run;
    },
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      setName("");
      setFiles([]);
      setError("");
      router.push(`/runs/${run.id}`);
    },
    onError: (e) => setError(e.message),
  });

  const addFiles = (list: FileList | null) =>
    list && setFiles((prev) => [...prev, ...Array.from(list)]);
  const canStart =
    name.trim().length > 0 && files.length > 0 && !start.isPending;

  return (
    <div className="flex h-full flex-col p-5">
      <div className="mb-1 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-neutral-400" />
        <h2 className="text-sm font-semibold text-neutral-900">
          New migration
        </h2>
      </div>
      <p className="mb-4 text-xs leading-relaxed text-neutral-500">
        Upload a client&rsquo;s employee files (CSV or Excel). The assistant
        sorts out the columns, cleans things up, combines everyone into one
        list, and only asks when it&rsquo;s genuinely unsure.
      </p>

      <label className="block text-xs font-medium text-neutral-700">
        Migration name
        <input
          className="mt-1 w-full rounded-lg border px-3 py-2 text-sm outline-none focus:border-neutral-400"
          placeholder="e.g. Acme Corp — HRIS to Darwinbox"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <div
        className={`mt-4 rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          dragging ? "border-neutral-500 bg-neutral-50" : "border-neutral-200"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <UploadCloud className="mx-auto h-6 w-6 text-neutral-400" />
        <p className="mt-2 text-xs text-neutral-600">
          Drag &amp; drop files, or{" "}
          <button
            className="font-medium text-neutral-900 underline"
            onClick={() => fileInput.current?.click()}
            type="button"
          >
            browse
          </button>
        </p>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center gap-2 rounded-lg bg-neutral-50 px-3 py-2 text-xs"
            >
              <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
              <span className="min-w-0 flex-1 truncate text-neutral-700">
                {f.name}
              </span>
              <button
                className="text-neutral-400 hover:text-neutral-700"
                onClick={() => setFiles(files.filter((_, j) => j !== i))}
                type="button"
                aria-label={`Remove ${f.name}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}

      <button
        className="mt-5 w-full rounded-lg bg-neutral-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-40"
        disabled={!canStart}
        onClick={() => start.mutate()}
        type="button"
      >
        {start.isPending ? "Starting…" : "Start migration"}
      </button>
      <p className="mt-2 text-center text-[11px] text-neutral-400">
        Runs in the background — you&rsquo;ll watch it work on the right.
      </p>
    </div>
  );
}
