"use client";

import { useState } from "react";
import { copyCitation } from "@/lib/api";
import type { CitationForm, Verification } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  verified: "border-emerald-200 bg-emerald-50 text-emerald-800",
  partially_verified: "border-amber-200 bg-amber-50 text-amber-800",
  needs_review: "border-red-200 bg-red-50 text-red-800",
  user_confirmed: "border-sky-200 bg-sky-50 text-sky-800",
};

const STATUS_MARKS: Record<string, string> = {
  verified: "✓",
  partially_verified: "◐",
  needs_review: "!",
  user_confirmed: "✓",
};

export function StatusBadge({ verification }: { verification: Pick<Verification, "status" | "label" | "summary"> }) {
  return (
    <span
      title={verification.summary}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[verification.status]}`}
    >
      <span aria-hidden>{STATUS_MARKS[verification.status]}</span>
      {verification.label}
    </span>
  );
}

/** Citation text with italics and small caps. The markup is generated and escaped by the API. */
export function CitationText({ form, className = "" }: { form: Pick<CitationForm, "html">; className?: string }) {
  return <span className={`citation ${className}`} dangerouslySetInnerHTML={{ __html: form.html }} />;
}

export function CopyButton({ form, label = "Copy" }: { form: Pick<CitationForm, "text" | "html">; label?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <button
      type="button"
      className="btn shrink-0 !px-2 !py-1 text-xs"
      onClick={async () => {
        setState((await copyCitation(form.text, form.html)) ? "copied" : "failed");
        window.setTimeout(() => setState("idle"), 1600);
      }}
    >
      {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label}
    </button>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {children}
    </div>
  );
}

export function Notice({ children }: { children: React.ReactNode }) {
  return <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">{children}</div>;
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="card border-dashed px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-soft">{children}</div>}
    </div>
  );
}

export function StyleSelect({ value, onChange, id }: { value: string; onChange: (style: string) => void; id?: string }) {
  return (
    <select id={id} className="input !w-auto" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Citation style">
      <option value="oscola">OSCOLA</option>
      <option value="bluebook">Bluebook</option>
      <option value="apa">APA 7th</option>
    </select>
  );
}
