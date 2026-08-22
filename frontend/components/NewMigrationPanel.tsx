"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileSpreadsheet,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { apiPost, apiUpload, apiUploadSingle } from "@/lib/api";
import type { Run, SchemaPreview, SchemaResponse } from "@/lib/types";
import { pluralize } from "@/lib/labels";

const TYPE_COLORS: Record<string, string> = {
  string: "bg-blue-50 text-blue-700",
  email: "bg-violet-50 text-violet-700",
  date: "bg-amber-50 text-amber-700",
  number: "bg-emerald-50 text-emerald-700",
  enum: "bg-rose-50 text-rose-700",
};

/** Left rail: the persistent "start a migration" panel. Stays mounted while
 *  the right pane switches between the list and a run's detail. */
export function NewMigrationPanel() {
  const router = useRouter();
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const schemaInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  // Schema state
  const [schemaFile, setSchemaFile] = useState<File | null>(null);
  const [schemaPreview, setSchemaPreview] = useState<SchemaPreview | null>(null);
  const [schemaDragging, setSchemaDragging] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [schemaError, setSchemaError] = useState("");

  const start = useMutation({
    mutationFn: async () => {
      const run = await apiPost<Run>("/api/runs", { name });
      // Upload custom schema first (if provided)
      if (schemaFile) {
        await apiUploadSingle(`/api/runs/${run.id}/schema`, schemaFile);
      }
      await apiUpload(`/api/runs/${run.id}/files`, files);
      await apiPost(`/api/runs/${run.id}/start`);
      return run;
    },
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      setName("");
      setFiles([]);
      setSchemaFile(null);
      setSchemaPreview(null);
      setSchemaOpen(false);
      setError("");
      setSchemaError("");
      router.push(`/runs/${run.id}`);
    },
    onError: (e) => setError(e.message),
  });

  const addFiles = (list: FileList | null) =>
    list && setFiles((prev) => [...prev, ...Array.from(list)]);

  const handleSchemaFile = async (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["yaml", "yml", "json"].includes(ext)) {
      setSchemaError("Only .yaml, .yml, or .json files are accepted.");
      return;
    }
    setSchemaFile(file);
    setSchemaError("");
    try {
      const preview = await apiUploadSingle<SchemaResponse>(
        "/api/runs/schema/preview",
        file
      );
      setSchemaPreview(preview.schema);
    } catch (e) {
      setSchemaFile(null);
      setSchemaPreview(null);
      setSchemaError(e instanceof Error ? e.message : "Could not parse schema.");
    }
  };

  const removeSchema = () => {
    setSchemaFile(null);
    setSchemaPreview(null);
    setSchemaError("");
  };

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
        Upload a client&rsquo;s{" "}
        {schemaPreview ? pluralize(schemaPreview.entity) : "data"} files (CSV
        or Excel). The assistant sorts out the columns, cleans things up,
        combines everyone into one list, and only asks when it&rsquo;s
        genuinely unsure.
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

      {/* --- Data files upload --- */}
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

      {/* --- Custom target schema (optional, collapsible) --- */}
      <div className="mt-4">
        <button
          className="flex w-full items-center gap-1.5 text-xs font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
          onClick={() => setSchemaOpen(!schemaOpen)}
          type="button"
        >
          {schemaOpen ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
          Custom target schema
          <span className="font-normal text-neutral-400">(optional)</span>
        </button>

        {schemaOpen && (
          <div className="mt-2 space-y-2">
            {!schemaFile ? (
              <>
                <div
                  className={`rounded-lg border-2 border-dashed p-4 text-center transition-colors ${
                    schemaDragging
                      ? "border-violet-400 bg-violet-50/50"
                      : "border-neutral-200"
                  }`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setSchemaDragging(true);
                  }}
                  onDragLeave={() => setSchemaDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setSchemaDragging(false);
                    const f = e.dataTransfer.files[0];
                    if (f) void handleSchemaFile(f);
                  }}
                >
                  <FileCode2 className="mx-auto h-5 w-5 text-neutral-400" />
                  <p className="mt-1.5 text-[11px] text-neutral-500">
                    Drop a YAML or JSON schema, or{" "}
                    <button
                      className="font-medium text-neutral-800 underline"
                      onClick={() => schemaInput.current?.click()}
                      type="button"
                    >
                      browse
                    </button>
                  </p>
                  <p className="mt-1 text-[10px] text-neutral-400">
                    Leave empty to use the default employee schema.
                  </p>
                  <input
                    ref={schemaInput}
                    type="file"
                    accept=".yaml,.yml,.json"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void handleSchemaFile(f);
                    }}
                  />
                </div>
              </>
            ) : (
              <>
                {/* Schema file chip */}
                <div className="flex items-center gap-2 rounded-lg bg-violet-50 px-3 py-2 text-xs">
                  <FileCode2 className="h-3.5 w-3.5 shrink-0 text-violet-500" />
                  <span className="min-w-0 flex-1 truncate text-violet-800">
                    {schemaFile.name}
                  </span>
                  <button
                    className="text-violet-400 hover:text-violet-700"
                    onClick={removeSchema}
                    type="button"
                    aria-label="Remove schema"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                {/* Schema preview */}
                {schemaPreview && (
                  <div className="rounded-lg border bg-white p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[11px] font-medium text-neutral-500 uppercase tracking-wide">
                        Schema Preview
                      </span>
                      <span className="text-[10px] text-neutral-400">
                        {schemaPreview.field_count} fields
                      </span>
                    </div>
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {schemaPreview.fields.map((f) => (
                        <div
                          key={f.name}
                          className="flex items-center gap-2 text-[11px]"
                        >
                          <span
                            className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
                              TYPE_COLORS[f.type] ||
                              "bg-neutral-100 text-neutral-600"
                            }`}
                          >
                            {f.type}
                          </span>
                          <span className="text-neutral-800">{f.name}</span>
                          {f.required && (
                            <span className="text-rose-400">*</span>
                          )}
                          {f.aliases.length > 0 && (
                            <span className="truncate text-neutral-400">
                              ({f.aliases.slice(0, 3).join(", ")}
                              {f.aliases.length > 3 && "…"})
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {!schemaPreview && (
                  <p className="text-[11px] text-neutral-400 italic">
                    Preview unavailable. Choose a valid YAML or JSON schema.
                  </p>
                )}
              </>
            )}

            {schemaError && (
              <p className="text-[11px] text-rose-600">{schemaError}</p>
            )}
          </div>
        )}
      </div>

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
