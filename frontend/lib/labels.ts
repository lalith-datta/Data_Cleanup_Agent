/**
 * Shared vocabulary — the single place where the app's internal names become
 * language a non-technical implementation consultant understands.
 *
 * Nothing here changes behaviour; it only translates field keys, status
 * enums, and escalation types into plain English. Every component reads from
 * this module so the wording stays consistent across the whole UI.
 */

// ---------------------------------------------------------------- field names
const FIELD_LABELS: Record<string, string> = {
  employee_id: "Employee ID",
  full_name: "Full name",
  email: "Email",
  phone: "Phone",
  department: "Department",
  job_title: "Job title",
  date_of_joining: "Date of joining",
  date_of_birth: "Date of birth",
  manager_email: "Manager's email",
  location: "Location",
  employment_status: "Employment status",
  salary: "Salary",
};

export function fieldLabel(key: string): string {
  return (
    FIELD_LABELS[key] ??
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

// ---------------------------------------------------------- entity naming
/** Naive but effective English pluralizer for entity nouns like "employee"
 *  or "customer" — good enough for the schema-declared `entity` name,
 *  which is always a plain singular noun. */
export function pluralize(word: string): string {
  if (!word) return word;
  if (/(s|x|z|ch|sh)$/i.test(word)) return word + "es";
  if (/[^aeiou]y$/i.test(word)) return word.slice(0, -1) + "ies";
  return word + "s";
}

export function capitalize(word: string): string {
  return word ? word[0].toUpperCase() + word.slice(1) : word;
}

/** "a customer" / "an employee" — approximate but good enough for the
 *  schema-declared entity noun. */
export function withArticle(word: string): string {
  return `${/^[aeiou]/i.test(word) ? "an" : "a"} ${word}`;
}

/** "1 customer" / "3 customers" — the noun form to use for a given count. */
export function countNoun(n: number, entity: string): string {
  return `${n} ${n === 1 ? entity : pluralize(entity)}`;
}

// ---------------------------------------------------------------- tone system
export type Tone = "active" | "attention" | "success" | "error" | "neutral";

export interface StatusCopy {
  label: string;
  tone: Tone;
}

// ------------------------------------------------------------- run status
const RUN_STATUS: Record<string, StatusCopy> = {
  created: { label: "Ready to start", tone: "neutral" },
  ingesting: { label: "Reading your files", tone: "active" },
  mapping: { label: "Understanding the columns", tone: "active" },
  reconciling: { label: "Matching people across files", tone: "active" },
  cleaning: { label: "Tidying up the data", tone: "active" },
  validating: { label: "Double-checking everything", tone: "active" },
  awaiting_review: { label: "Waiting for your review", tone: "attention" },
  ready_to_push: { label: "Ready to send", tone: "success" },
  pushing: { label: "Sending to the new system", tone: "active" },
  completed: { label: "All done", tone: "success" },
  failed: { label: "Something went wrong", tone: "error" },
  rolled_back: { label: "Changes undone", tone: "neutral" },
};

export function runStatus(status: string): StatusCopy {
  return RUN_STATUS[status] ?? { label: status, tone: "neutral" };
}

// ------------------------------------------------------------- record status
const RECORD_STATUS: Record<string, StatusCopy> = {
  clean: { label: "Processing", tone: "neutral" },
  needs_review: { label: "Needs your input", tone: "attention" },
  valid: { label: "Ready to send", tone: "success" },
  invalid: { label: "Skipped", tone: "error" },
  pushed: { label: "Sent", tone: "success" },
  push_failed: { label: "Couldn't send", tone: "error" },
  rolled_back: { label: "Undone", tone: "neutral" },
};

export function recordStatus(status: string): StatusCopy {
  return RECORD_STATUS[status] ?? { label: status, tone: "neutral" };
}

// ---------------------------------------------------------- escalation copy
export interface EscalationCopy {
  /** short chip label */
  label: string;
  /** one-line explanation of what kind of question this is */
  blurb: string;
  tone: Tone;
}

const ESCALATION_COPY: Record<string, EscalationCopy> = {
  ambiguous_mapping: {
    label: "Which field?",
    blurb: "A column could belong to more than one field.",
    tone: "attention",
  },
  unmapped_column: {
    label: "Extra column",
    blurb: "A column doesn't clearly match any field.",
    tone: "neutral",
  },
  value_conflict: {
    label: "Which value?",
    blurb: "Two files disagree about the same person.",
    tone: "attention",
  },
  ambiguous_date: {
    label: "Which date format?",
    blurb: "A date could be read two different ways.",
    tone: "attention",
  },
  validation_failure: {
    label: "Needs a fix",
    blurb: "A value doesn't look right yet.",
    tone: "error",
  },
  manager_unresolved: {
    label: "Find the manager",
    blurb: "A manager needs a matching email address.",
    tone: "neutral",
  },
};

export function escalationCopy(type: string): EscalationCopy {
  return (
    ESCALATION_COPY[type] ?? { label: type, blurb: "", tone: "neutral" }
  );
}

// ------------------------------------------------------- people & values
/** Turn a reconciliation key like "email:priya.sharma@acme.com" or
 *  "id:E1003" into something readable when we don't have the real name. */
export function prettyKey(naturalKey: string, entity = "record"): string {
  if (!naturalKey) return `this ${entity}`;
  const [prefix, ...rest] = naturalKey.split(":");
  const value = rest.join(":") || prefix;
  if (prefix === "email") return value;
  if (prefix === "id") return `#${value}`;
  return value;
}

/** Build a lookup from reconciliation key → real full name, using the
 *  records already loaded on the page, so questions can say "Priya Sharma"
 *  instead of "email:priya.sharma@acme.com". */
export function buildNameMap(
  records: { natural_key: string; merged_json: Record<string, unknown> }[]
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const r of records) {
    const name = r.merged_json?.full_name;
    if (typeof name === "string" && name.trim()) map[r.natural_key] = name;
  }
  return map;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** ISO date -> "15 Mar 2021"; anything else passes through unchanged. */
export function prettyDate(value: unknown): string {
  if (typeof value !== "string") return String(value ?? "");
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return value;
  const [, y, mo, d] = m;
  const month = MONTHS[Number(mo) - 1] ?? mo;
  return `${Number(d)} ${month} ${y}`;
}

/** Human-friendly value for display: dates prettified, empties spelled out. */
export function prettyValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${fieldLabel(k)}: ${prettyValue(val)}`)
      .join(", ");
  }
  return prettyDate(v);
}
