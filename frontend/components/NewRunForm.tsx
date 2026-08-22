"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { apiPost, apiUpload } from "@/lib/api";
import type { Run } from "@/lib/types";

export default function NewRunForm() {
  const router = useRouter();
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
    onSuccess: (run) => router.push(`/runs/${run.id}`),
    onError: (e) => setError(e.message),
  });

  const canStart = name.trim().length > 0 && files.length > 0 && !start.isPending;

  return (
    <div className="rounded-xl border bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">New migration</h2>
      <p className="mt-1 text-sm text-neutral-500">
        Upload your client&rsquo;s employee files (CSV or Excel). The assistant
        will sort out the columns, clean things up, and combine everyone into
        one list — and only ask you about the cases it can&rsquo;t safely
        decide on its own.
      </p>

      <label className="mt-5 block text-sm font-medium">
        Migration name
        <input
          className="mt-1 w-full rounded-md border px-3 py-2 text-sm outline-none focus:border-neutral-400"
          placeholder="e.g. Acme Corp — HRIS to Darwinbox"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <div
        className={`mt-4 rounded-lg border-2 border-dashed p-8 text-center text-sm transition-colors ${
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
          setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
        }}
      >
        <p className="text-neutral-600">
          Drag &amp; drop files here, or{" "}
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
          onChange={(e) =>
            setFiles((prev) => [...prev, ...Array.from(e.target.files ?? [])])
          }
        />
      </div>

      {files.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center justify-between rounded-md bg-neutral-50 px-3 py-1.5"
            >
              <span>{f.name}</span>
              <button
                className="text-neutral-400 hover:text-neutral-700"
                onClick={() => setFiles(files.filter((_, j) => j !== i))}
                type="button"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <button
        className="mt-5 w-full rounded-md bg-neutral-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40"
        disabled={!canStart}
        onClick={() => start.mutate()}
        type="button"
      >
        {start.isPending ? "Starting agent…" : "Start migration"}
      </button>
    </div>
  );
}
