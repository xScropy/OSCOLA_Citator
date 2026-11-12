"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { CitationText, CopyButton, Empty, ErrorNote, Notice } from "@/components/ui";
import { api, ApiError, download } from "@/lib/api";
import type { Metadata, Pinpoint } from "@/lib/types";
import { TYPE_LABELS } from "@/lib/types";

type Text = { text: string; html: string };
type Occurrence = { footnote: number; page: string | null; form: "full" | "short" | "ibid" | "mention"; pinpoint: Pinpoint; raw: string };
type Authority = {
  id: number;
  type: string;
  metadata: Metadata;
  confident: boolean;
  library_id: number | null;
  first_footnote: number;
  citation: Text;
  full: Text;
  locations: string;
  footnotes: number[];
  occurrences: Occurrence[];
};
type Change = { types: string[]; labels: string[]; suggested: Text; accepted: boolean; edited: boolean };
type NoteCitation = { key: string; raw: string; form: string; authority_id: number | null; mention_ids: number[]; pinpoint: Pinpoint; change: Change | null; issue: string | null };
type Note = { number: number; page: string | null; original: Text; revised: Text; changed: boolean; citations: NoteCitation[]; end_change: { key: string; label: string; accepted: boolean } | null };
type Analysis = {
  style: string;
  document: { kind: "docx" | "pdf"; name: string; footnotes: number; pages: number | null; pages_available: boolean; location_unit: "page" | "footnote" };
  warnings: string[];
  stats: { authorities: number; citations: number; unrecognised: number; footnotes_changed: number; in_library: number };
  authorities: Authority[];
  footnotes: Note[];
  table: { title: string; location_heading: string; sections: { heading: string; entries: (Text & { id: number; pages: string })[] }[] };
};

const FORM_LABELS = { full: "full citation", short: "short form", ibid: "ibid", mention: "cited in the text of the note" };
const PIN_LABELS: Record<string, string> = { page: "p", para: "para", article: "art", section: "s" };
const TABS = [
  { id: "authorities", label: "Authorities" },
  { id: "footnotes", label: "Footnotes & corrections" },
  { id: "table", label: "Table of Authorities" },
] as const;

export default function DocumentsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [style, setStyle] = useState("oscola");
  const [shorten, setShorten] = useState(false);
  const [useIbid, setUseIbid] = useState(true);
  const [firstPage, setFirstPage] = useState("1");
  const [skip, setSkip] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("authorities");
  const [selected, setSelected] = useState<number[]>([]);
  const [onlyChanged, setOnlyChanged] = useState(true);
  const [message, setMessage] = useState("");
  const [tableFormat, setTableFormat] = useState("docx");
  const sequence = useRef(0);

  const form = useCallback(
    (extra: Record<string, string> = {}) => {
      const data = new FormData();
      data.append("file", file as File);
      data.append("style", style);
      data.append("options", JSON.stringify({ shorten, use_ibid: useIbid, first_page: Number(firstPage) || 1, skip, overrides }));
      for (const [key, value] of Object.entries(extra)) data.append(key, value);
      return data;
    },
    [file, style, shorten, useIbid, firstPage, skip, overrides],
  );

  // Re-analyse whenever the file, the options or the user's decisions change.
  useEffect(() => {
    if (!file) return;
    const run = ++sequence.current;
    setBusy(true);
    const timer = window.setTimeout(() => {
      api<Analysis>("/documents/analyze", "POST", form())
        .then((analysis) => {
          if (run !== sequence.current) return;
          setResult(analysis);
          setError("");
        })
        .catch((e: ApiError) => {
          if (run !== sequence.current) return;
          setError(e.message);
          setResult(null);
        })
        .finally(() => run === sequence.current && setBusy(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [file, form]);

  function choose(next: File | null) {
    setFile(next);
    setResult(null);
    setSkip([]);
    setOverrides({});
    setSelected([]);
    setMessage("");
    setError("");
  }

  async function save(path: string, extra: Record<string, string>) {
    setError("");
    try {
      await download(path, form(extra));
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function addToLibrary() {
    if (!result || !file) return;
    let added = 0;
    let existing = 0;
    let failed = 0;
    for (const authority of result.authorities.filter((a) => selected.includes(a.id))) {
      try {
        await api("/references", "POST", {
          metadata: authority.metadata,
          retrieved: authority.metadata,
          source: { name: `Extracted from ${file.name}`, url: "", reliable: false },
          style,
        });
        added += 1;
      } catch (e) {
        if ((e as ApiError).status === 409) existing += 1;
        else failed += 1;
      }
    }
    setSelected([]);
    setMessage(
      [`${added} added to your library`, existing ? `${existing} already there` : "", failed ? `${failed} could not be saved` : ""].filter(Boolean).join(" · ") +
        ". They are marked Partially Verified until you check them against the source.",
    );
    setOverrides({ ...overrides }); // triggers a fresh analysis, which now recognises the saved sources
  }

  const toggle = (key: string, accepted: boolean) => setSkip(accepted ? skip.filter((k) => k !== key) : [...skip, key]);
  const unit = result?.document.location_unit === "page" ? "Page" : "Footnote";
  const addable = result ? result.authorities.filter((a) => a.library_id === null) : [];
  const notes = result ? result.footnotes.filter((n) => !onlyChanged || n.changed || n.citations.some((c) => c.change || c.issue) || n.end_change) : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">Document Check</h1>
        <p className="mt-1 text-sm text-ink-soft">
          Upload a memorial, essay or article. CiteRight reads the footnotes, lists every authority and where it is cited, suggests corrections, and builds a table of authorities with page numbers.
        </p>
      </div>

      <section className="card space-y-4 p-4">
        <div>
          <label className="label" htmlFor="document">
            PDF or Word document (.docx), up to 25 MB
          </label>
          <input
            id="document"
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-paper-line file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-paper"
            onChange={(e) => choose(e.target.files?.[0] || null)}
          />
          <p className="mt-1 text-xs text-ink-faint">The file is analysed and then discarded. It is not stored.</p>
        </div>
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div>
            <label className="label" htmlFor="doc-style">
              Citation style
            </label>
            <select id="doc-style" className="input !w-auto" value={style} onChange={(e) => setStyle(e.target.value)}>
              <option value="oscola">OSCOLA</option>
              <option value="bluebook">Bluebook</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="first-page">
              Number of the first page
            </label>
            <input id="first-page" type="number" className="input !w-28" value={firstPage} onChange={(e) => setFirstPage(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 pb-1.5 text-sm">
            <input type="checkbox" checked={shorten} onChange={(e) => setShorten(e.target.checked)} />
            Shorten every citation after the first
          </label>
          <label className={`flex items-center gap-2 pb-1.5 text-sm ${shorten ? "" : "opacity-50"}`}>
            <input type="checkbox" checked={useIbid} disabled={!shorten} onChange={(e) => setUseIbid(e.target.checked)} />
            Use ibid for consecutive citations
          </label>
        </div>
      </section>

      <ErrorNote>{error}</ErrorNote>
      {busy && !result && <p className="text-sm text-ink-faint">Reading the document…</p>}

      {result && (
        <>
          {result.warnings.map((warning) => (
            <Notice key={warning}>{warning}</Notice>
          ))}

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              { label: "Footnotes read", value: result.document.footnotes },
              { label: "Authorities found", value: result.stats.authorities },
              { label: "Footnotes with corrections", value: result.stats.footnotes_changed },
              { label: "Passages not recognised", value: result.stats.unrecognised },
            ].map((item) => (
              <div key={item.label} className="card p-4">
                <p className="text-3xl font-semibold tabular-nums">{item.value}</p>
                <p className="mt-1 text-sm text-ink-soft">{item.label}</p>
              </div>
            ))}
          </div>

          {result.document.footnotes > 0 && (
            <section className="card flex flex-wrap items-center gap-2 p-4">
              <span className="mr-auto text-sm font-medium">Download {busy && <span className="font-normal text-ink-faint">· updating…</span>}</span>
              {result.document.kind === "docx" ? (
                <button className="btn-primary" onClick={() => save("/documents/export", { output: "corrected" })}>
                  Corrected Word document
                </button>
              ) : (
                <span className="text-xs text-ink-soft">PDFs cannot be edited in place. Download the revised footnotes instead.</span>
              )}
              <button className="btn" onClick={() => save("/documents/export", { output: "footnotes", format: "docx" })}>
                Revised footnotes (DOCX)
              </button>
              <button className="btn" onClick={() => save("/documents/export", { output: "footnotes", format: "txt" })}>
                Revised footnotes (TXT)
              </button>
            </section>
          )}

          <div className="flex gap-1 overflow-x-auto border-b border-paper-line">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm ${tab === t.id ? "border-brand font-medium text-brand" : "border-transparent text-ink-soft hover:text-ink"}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "authorities" &&
            (result.authorities.length === 0 ? (
              <Empty title="No authorities were recognised">Check that the document has numbered footnotes with citations in them.</Empty>
            ) : (
              <section className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      disabled={addable.length === 0}
                      checked={addable.length > 0 && addable.every((a) => selected.includes(a.id))}
                      onChange={(e) => setSelected(e.target.checked ? addable.map((a) => a.id) : [])}
                    />
                    Select all not yet in the library
                  </label>
                  <button className="btn-primary ml-auto" disabled={selected.length === 0} onClick={addToLibrary}>
                    Add to library{selected.length > 0 && ` (${selected.length})`}
                  </button>
                </div>
                {message && (
                  <p role="status" className="text-sm text-emerald-700">
                    {message}
                  </p>
                )}
                <ul className="space-y-3">
                  {result.authorities.map((a) => (
                    <li key={a.id} className="card flex gap-3 p-4">
                      <input
                        type="checkbox"
                        className="mt-1.5"
                        aria-label={`Select ${a.metadata.title}`}
                        disabled={a.library_id !== null}
                        checked={selected.includes(a.id)}
                        onChange={(e) => setSelected(e.target.checked ? [...selected, a.id] : selected.filter((id) => id !== a.id))}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                          <span className="font-medium uppercase tracking-wide">{TYPE_LABELS[a.type] || a.type}</span>
                          {a.library_id !== null && (
                            <Link href={`/library/view?id=${a.library_id}`} className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-emerald-800 hover:underline">
                              In your library
                            </Link>
                          )}
                          {!a.confident && a.library_id === null && <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-800">Check details</span>}
                        </div>
                        <p>
                          <CitationText form={a.full} />
                        </p>
                        <p className="mt-1.5 text-sm">
                          <span className="text-ink-soft">
                            {unit}
                            {a.locations.includes(",") || a.locations.includes("–") ? "s" : ""}:
                          </span>{" "}
                          <span className="font-medium">{a.locations}</span>
                          <span className="text-ink-soft"> · cited {a.occurrences.length} {a.occurrences.length === 1 ? "time" : "times"}</span>
                        </p>
                        <details className="mt-1.5 text-sm">
                          <summary className="cursor-pointer text-ink-soft hover:text-ink">Every citation and pinpoint</summary>
                          <ul className="mt-1.5 space-y-1 border-l-2 border-paper-line pl-3">
                            {a.occurrences.map((o, index) => (
                              <li key={index}>
                                <span className="font-medium">Footnote {o.footnote}</span>
                                {o.page && <span className="text-ink-soft"> · page {o.page}</span>}
                                <span className="text-ink-soft"> · {FORM_LABELS[o.form]}</span>
                                {o.pinpoint && (
                                  <span>
                                    {" "}
                                    · pinpoint {PIN_LABELS[o.pinpoint.kind]} {o.pinpoint.value}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </details>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <CopyButton form={a.full} />
                          <Link className="btn !px-2 !py-1 text-xs" href={`/generate?q=${encodeURIComponent(String(a.metadata.title || ""))}`}>
                            Look up official record
                          </Link>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))}

          {tab === "footnotes" && (
            <section className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <p className="text-ink-soft">Untick a correction to keep your original wording, or edit the suggestion. Text that is not a citation is never changed.</p>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
                  Only footnotes with suggestions
                </label>
              </div>
              {notes.length === 0 && <Empty title="No corrections to suggest">The citations that were recognised already follow the style.</Empty>}
              <ul className="space-y-3">
                {notes.map((note) => (
                  <li key={note.number} className="card p-4">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-soft">
                      Footnote {note.number}
                      {note.page && ` · page ${note.page}`}
                    </p>
                    <div className={note.changed ? "grid gap-3 md:grid-cols-2" : ""}>
                      <div>
                        {note.changed && <p className="label">Original</p>}
                        <p className={`whitespace-pre-line rounded-md px-3 py-2 ${note.changed ? "bg-red-50/60" : "bg-paper"}`}>
                          <CitationText form={note.original} />
                        </p>
                      </div>
                      {note.changed && (
                        <div>
                          <div className="flex items-center justify-between">
                            <p className="label">Revised</p>
                            <CopyButton form={note.revised} />
                          </div>
                          <p className="whitespace-pre-line rounded-md bg-emerald-50/70 px-3 py-2">
                            <CitationText form={note.revised} />
                          </p>
                        </div>
                      )}
                    </div>
                    <ul className="mt-3 space-y-2 text-sm">
                      {note.citations
                        .filter((c) => c.change || c.issue)
                        .map((c) => (
                          <li key={c.key}>
                            {c.change && (
                              <div className="flex flex-wrap items-center gap-2">
                                <label className="flex items-center gap-2">
                                  <input type="checkbox" checked={!skip.includes(c.key)} onChange={(e) => toggle(c.key, e.target.checked)} />
                                  <span className="font-medium">{c.change.labels.join(", ")}</span>
                                </label>
                                <input
                                  key={`${c.key}-${c.change.suggested.text}`}
                                  className="input min-w-0 flex-1 font-serif"
                                  aria-label={`Suggested citation for footnote ${note.number}`}
                                  defaultValue={c.change.suggested.text}
                                  disabled={skip.includes(c.key)}
                                  onBlur={(e) => {
                                    const value = e.target.value.trim();
                                    if (value && value !== c.change!.suggested.text) setOverrides({ ...overrides, [c.key]: value });
                                  }}
                                />
                                {c.change.edited && (
                                  <button
                                    className="btn !px-2 !py-1 text-xs"
                                    onClick={() => {
                                      const next = { ...overrides };
                                      delete next[c.key];
                                      setOverrides(next);
                                    }}
                                  >
                                    Reset
                                  </button>
                                )}
                              </div>
                            )}
                            {c.issue && <p className="text-amber-800">⚠ {c.issue}</p>}
                          </li>
                        ))}
                      {note.end_change && (
                        <li>
                          <label className="flex items-center gap-2">
                            <input type="checkbox" checked={!skip.includes(note.end_change.key)} onChange={(e) => toggle(note.end_change!.key, e.target.checked)} />
                            <span className="font-medium">{note.end_change.label}</span>
                          </label>
                        </li>
                      )}
                    </ul>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {tab === "table" && (
            <section className="card p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-paper-line pb-4">
                <p className="text-sm text-ink-soft">
                  Every {result.document.location_unit} on which each authority is cited, whether in full, in short form or by ibid.
                </p>
                <div className="flex items-center gap-2">
                  <select className="input !w-auto" aria-label="Table format" value={tableFormat} onChange={(e) => setTableFormat(e.target.value)}>
                    <option value="docx">Word (DOCX)</option>
                    <option value="pdf">PDF</option>
                    <option value="txt">Plain text (TXT)</option>
                  </select>
                  <button className="btn-primary" disabled={result.table.sections.length === 0} onClick={() => save("/documents/export", { output: "table", format: tableFormat })}>
                    Export
                  </button>
                </div>
              </div>
              <h2 className="mb-4 font-serif text-2xl font-semibold">{result.table.title}</h2>
              {result.table.sections.length === 0 && <p className="text-sm text-ink-soft">No authorities were recognised.</p>}
              <div className="space-y-5">
                {result.table.sections.map((section) => (
                  <div key={section.heading}>
                    <div className="mb-1 flex justify-between text-sm font-semibold uppercase tracking-wide text-ink-soft">
                      <span>{section.heading}</span>
                      <span>{result.table.location_heading}</span>
                    </div>
                    {section.entries.map((entry) => (
                      <div key={entry.id} className="flex items-baseline gap-3 py-1">
                        <p className="min-w-0 flex-1 pl-6 -indent-6">
                          <CitationText form={entry} />
                        </p>
                        <span className="shrink-0 font-serif text-[15px] tabular-nums">{entry.pages}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
