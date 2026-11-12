"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "@/components/AppShell";
import ReferenceEditor, { type Draft } from "@/components/ReferenceEditor";
import { CitationText, ErrorNote, Notice, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Candidate, IdentifyResult, Reference } from "@/lib/types";
import { TYPE_LABELS } from "@/lib/types";

const KIND_LABELS = { doi: "DOI", isbn: "ISBN", url: "web address", text: "title or name" };
const MATCH_LABELS = { identifier: "Identifier match", exact_title: "Exact title match", search: "Search result" };

export default function GeneratePage() {
  const { user } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const [query, setQuery] = useState(params.get("q") || "");
  const [type, setType] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<IdentifyResult | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saved, setSaved] = useState<Reference | null>(null);

  const blank = useCallback(
    (title = ""): Draft => ({
      metadata: { type: type || "book", title },
      pinpoint: null,
      style: user.default_style,
      notes: "",
      tags: [],
      favorite: false,
      user_confirmed: false,
      collection_ids: [],
    }),
    [type, user.default_style],
  );

  const search = useCallback(
    async (text: string, typeHint: string) => {
      if (text.trim().length < 2) return;
      setBusy(true);
      setError("");
      setResult(null);
      setDraft(null);
      setSaved(null);
      try {
        setResult(await api<IdentifyResult>("/identify", "POST", { query: text.trim(), type: typeHint || null }));
      } catch (e) {
        setError((e as ApiError).message);
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  useEffect(() => {
    const initial = params.get("q");
    if (initial) search(initial, "");
    else if (params.get("manual")) setDraft(blank());
    // run once for the query the page was opened with
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function choose(candidate: Candidate) {
    setDraft({ ...blank(), metadata: candidate.metadata, retrieved: candidate.metadata, source: candidate.source });
    window.scrollTo({ top: 0 });
  }

  if (saved) {
    return (
      <div className="space-y-5">
        <h1 className="h1">Saved to your library</h1>
        <div className="card p-4">
          <CitationText form={saved.citations.forms.full} />
          <div className="mt-2">
            <StatusBadge verification={saved.verification} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-primary"
            onClick={() => {
              setSaved(null);
              setResult(null);
              setQuery("");
            }}
          >
            Cite another source
          </button>
          <Link className="btn" href={`/library/view?id=${saved.id}`}>
            Open reference
          </Link>
          <Link className="btn" href="/library">
            Go to My Library
          </Link>
        </div>
      </div>
    );
  }

  if (draft) {
    return (
      <div className="space-y-5">
        <div>
          <button className="text-sm text-ink-soft underline" onClick={() => setDraft(null)}>
            ← Back to results
          </button>
          <h1 className="h1 mt-2">{draft.source ? "Review and save" : "Enter source manually"}</h1>
          <p className="mt-1 text-sm text-ink-soft">
            {draft.source
              ? "Check the retrieved details against the source. Anything you change is marked as edited."
              : "Fill in what you know. Missing details are left out of the citation and flagged, never guessed."}
          </p>
        </div>
        <ReferenceEditor
          key={JSON.stringify(draft.retrieved || null)}
          draft={draft}
          onSaved={(ref) => {
            setSaved(ref);
            setDraft(null);
          }}
          onCancel={() => setDraft(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">Citation Generator</h1>
        <p className="mt-1 text-sm text-ink-soft">Enter whatever you have: a case name, ISBN, DOI, book or article title, treaty name, or a URL.</p>
      </div>

      <form
        className="card space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          router.replace(`/generate?q=${encodeURIComponent(query.trim())}`);
          search(query, type);
        }}
      >
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            className="input !py-2.5 !text-base"
            placeholder="Donoghue v Stevenson · 9780198864473 · 10.1093/… · https://…"
            aria-label="Source to identify"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <select className="input sm:!w-48" aria-label="Limit to a source type" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">Any source type</option>
            {Object.entries(TYPE_LABELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
          <button className="btn-primary !px-5" disabled={busy || query.trim().length < 2}>
            {busy ? "Searching…" : "Find source"}
          </button>
        </div>
        <p className="text-sm text-ink-soft">
          Can’t find it?{" "}
          <button type="button" className="underline" onClick={() => setDraft(blank(result?.input_kind === "text" ? result.query : ""))}>
            Enter the source manually
          </button>
        </p>
      </form>

      <ErrorNote>{error}</ErrorNote>

      {result && (
        <section className="space-y-3">
          <p className="text-sm text-ink-soft">
            Read as a <strong className="font-medium text-ink">{KIND_LABELS[result.input_kind]}</strong>
            {result.candidates.length > 0 && ` · ${result.candidates.length} possible ${result.candidates.length === 1 ? "source" : "sources"}`}
          </p>
          {result.warnings.map((warning) => (
            <Notice key={warning}>{warning}</Notice>
          ))}
          {result.message && <p className="text-sm font-medium">{result.message}</p>}
          <ul className="space-y-3">
            {result.candidates.map((candidate, index) => (
              <li key={index} className="card p-4">
                <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                  <span className="font-medium uppercase tracking-wide">{TYPE_LABELS[candidate.metadata.type]}</span>
                  <span>· {MATCH_LABELS[candidate.match]}</span>
                  <span>
                    ·{" "}
                    {candidate.source.url ? (
                      <a className="underline" href={candidate.source.url} target="_blank" rel="noreferrer">
                        {candidate.source.name}
                      </a>
                    ) : (
                      candidate.source.name
                    )}
                  </span>
                </div>
                <p>
                  <CitationText form={candidate.citations.forms.full} />
                </p>
                {candidate.citations.missing.required.length > 0 && (
                  <p className="mt-1 text-xs text-amber-800">The source record does not give: {candidate.citations.missing.required.join(", ")}</p>
                )}
                <button className="btn-primary mt-3" onClick={() => choose(candidate)}>
                  Use this source
                </button>
              </li>
            ))}
          </ul>
          {result.candidates.length === 0 && (
            <button className="btn-primary" onClick={() => setDraft(blank(result.input_kind === "text" ? result.query : ""))}>
              Enter the source manually
            </button>
          )}
        </section>
      )}
    </div>
  );
}
