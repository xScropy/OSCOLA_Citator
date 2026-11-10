"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Citations, Collection, Duplicate, Metadata, Pinpoint, Reference, Source, Verification } from "@/lib/types";
import MetadataForm from "./MetadataForm";
import { CitationText, CopyButton, ErrorNote, Notice, StatusBadge, StyleSelect } from "./ui";

export type Draft = {
  id?: number;
  metadata: Metadata;
  retrieved?: Metadata | null;
  source?: Source | null;
  pinpoint: Pinpoint;
  style: string;
  notes: string;
  tags: string[];
  favorite: boolean;
  user_confirmed: boolean;
  collection_ids: number[];
};

type Preview = { citations: Citations; verification: Verification };

const PINPOINT_KINDS = [
  { id: "page", label: "Page" },
  { id: "para", label: "Paragraph" },
  { id: "article", label: "Article" },
  { id: "section", label: "Section" },
];

const CHECK_NOTES: Record<string, string> = { edited: "edited since retrieval", unverified: "not confirmed by a source" };
const CHECK_MARKS: Record<string, string> = { confirmed: "✓", edited: "✎", unverified: "?", missing: "–" };
const CHECK_TEXT: Record<string, string> = {
  confirmed: "matches the source",
  edited: "edited since retrieval",
  unverified: "not confirmed by a source",
  missing: "missing",
};

export default function ReferenceEditor({ draft, onSaved, onCancel }: { draft: Draft; onSaved: (ref: Reference) => void; onCancel?: () => void }) {
  const [metadata, setMetadata] = useState<Metadata>(draft.metadata);
  const [pinpoint, setPinpoint] = useState<{ kind: string; value: string }>(draft.pinpoint || { kind: "page", value: "" });
  const [style, setStyle] = useState(draft.style);
  const [notes, setNotes] = useState(draft.notes);
  const [tags, setTags] = useState(draft.tags.join(", "));
  const [favorite, setFavorite] = useState(draft.favorite);
  const [confirmed, setConfirmed] = useState(draft.user_confirmed);
  const [collectionIds, setCollectionIds] = useState<number[]>(draft.collection_ids);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [duplicates, setDuplicates] = useState<Duplicate[]>([]);
  const sequence = useRef(0);

  useEffect(() => {
    api<Collection[]>("/collections").then(setCollections).catch(() => setCollections([]));
  }, []);

  // Regenerate the citation whenever the metadata, pinpoint or style changes.
  useEffect(() => {
    const run = ++sequence.current;
    const timer = window.setTimeout(() => {
      api<Preview>("/cite", "POST", { metadata, pinpoint, style, retrieved: draft.retrieved, source: draft.source, user_confirmed: confirmed })
        .then((result) => {
          if (run === sequence.current) {
            setPreview(result);
            setPreviewError("");
          }
        })
        .catch((e: ApiError) => run === sequence.current && setPreviewError(e.message));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [metadata, pinpoint, style, confirmed, draft.retrieved, draft.source]);

  const flagged: Record<string, string> = {};
  for (const check of preview?.verification.checks || []) {
    if (CHECK_NOTES[check.state]) flagged[check.field] = CHECK_NOTES[check.state];
  }

  async function save(allowDuplicate = false) {
    setSaving(true);
    setError("");
    const common = {
      metadata,
      style,
      notes,
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      favorite,
      user_confirmed: confirmed,
      collection_ids: collectionIds,
    };
    try {
      const saved = draft.id
        ? await api<Reference>(`/references/${draft.id}`, "PATCH", { ...common, pinpoint, clear_pinpoint: !pinpoint.value.trim() })
        : await api<Reference>("/references", "POST", { ...common, pinpoint, retrieved: draft.retrieved, source: draft.source, allow_duplicate: allowDuplicate });
      setDuplicates([]);
      onSaved(saved);
    } catch (e) {
      const err = e as ApiError;
      const detail = err.detail as { duplicates?: Duplicate[] } | null;
      if (err.status === 409 && detail?.duplicates) setDuplicates(detail.duplicates);
      else setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const missing = preview?.citations.missing;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <section className="card p-4">
          <h2 className="h2 mb-3">Source details</h2>
          <MetadataForm metadata={metadata} onChange={setMetadata} flagged={flagged} />
        </section>

        <section className="card p-4">
          <h2 className="h2 mb-1">Pinpoint</h2>
          <p className="mb-3 text-xs text-ink-soft">The specific page, paragraph, article or section you are citing. It is kept separate from the source itself.</p>
          <div className="flex gap-2">
            <select className="input !w-36" aria-label="Pinpoint type" value={pinpoint.kind} onChange={(e) => setPinpoint({ ...pinpoint, kind: e.target.value })}>
              {PINPOINT_KINDS.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.label}
                </option>
              ))}
            </select>
            <input className="input" aria-label="Pinpoint reference" placeholder="e.g. 45, 32–35, 19(2)" value={pinpoint.value} onChange={(e) => setPinpoint({ ...pinpoint, value: e.target.value })} />
          </div>
        </section>

        <section className="card space-y-3 p-4">
          <h2 className="h2">Research notes</h2>
          <div>
            <label className="label" htmlFor="tags">
              Tags (comma separated)
            </label>
            <input id="tags" className="input" placeholder="Proportionality, Admissibility" value={tags} onChange={(e) => setTags(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="notes">
              Notes: why this authority matters, the proposition it supports, key paragraphs
            </label>
            <textarea id="notes" className="input min-h-24" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          {collections.length > 0 && (
            <fieldset>
              <legend className="label">Collections</legend>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {collections.map((c) => (
                  <label key={c.id} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={collectionIds.includes(c.id)}
                      onChange={(e) => setCollectionIds(e.target.checked ? [...collectionIds, c.id] : collectionIds.filter((id) => id !== c.id))}
                    />
                    {c.name}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={favorite} onChange={(e) => setFavorite(e.target.checked)} />
            Mark as favourite
          </label>
        </section>

        {duplicates.length > 0 && (
          <section className="card border-amber-300 bg-amber-50 p-4">
            <h2 className="font-medium">This source may already be in your library</h2>
            <ul className="mt-2 space-y-2">
              {duplicates.map((d) => (
                <li key={d.id} className="rounded-md border border-amber-200 bg-white p-3">
                  <CitationText form={d.citation} />
                  <p className="mt-1 text-xs text-ink-soft">
                    {d.reasons.join(" · ")} ·{" "}
                    <Link className="underline" href={`/library/${d.id}`}>
                      Open existing reference
                    </Link>
                  </p>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="btn" disabled={saving} onClick={() => save(true)}>
                Save as a separate reference
              </button>
              <button type="button" className="btn" onClick={() => setDuplicates([])}>
                Don’t save
              </button>
            </div>
            <p className="mt-2 text-xs text-ink-soft">Nothing is merged automatically. You can merge duplicates from My Library.</p>
          </section>
        )}

        <ErrorNote>{error}</ErrorNote>
        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" disabled={saving || !String(metadata.title || "").trim()}>
            {saving ? "Saving…" : draft.id ? "Save changes" : "Save to library"}
          </button>
          {onCancel && (
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          )}
        </div>
      </form>

      <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <section className="card p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="h2">Citation preview</h2>
            <StyleSelect value={style} onChange={setStyle} />
          </div>
          <ErrorNote>{previewError}</ErrorNote>
          {!preview && !previewError && <p className="text-sm text-ink-faint">Generating…</p>}
          {preview && (
            <div className="space-y-3">
              {(["footnote", "short", "bibliography"] as const).map((key) => {
                const form = preview.citations.forms[key];
                return (
                  <div key={key}>
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-ink-soft">{form.label}</span>
                      <CopyButton form={form} />
                    </div>
                    <p className="rounded-md bg-paper px-3 py-2">
                      <CitationText form={form} />
                    </p>
                  </div>
                );
              })}
              {style === "oscola" && <p className="text-xs text-ink-faint">Replace “n #” with the number of the footnote where the source is first cited.</p>}
              {style === "bluebook" && <p className="text-xs text-ink-faint">Replace “note #” with the first footnote. Journal and court names are printed as entered; abbreviate them per the Bluebook tables.</p>}
              {style === "apa" && <p className="text-xs text-ink-faint">APA uses sentence case for titles. Titles are printed as entered, so adjust the capitalisation in the title field.</p>}
            </div>
          )}
        </section>

        {missing && missing.required.length > 0 && (
          <Notice>
            <p className="font-medium">Missing details</p>
            <p className="mt-0.5">
              {missing.required.join(", ")}. These were left out of the citation rather than guessed. Add them from the source itself.
            </p>
          </Notice>
        )}

        {preview && (
          <section className="card p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h2 className="h2">Verification</h2>
              <StatusBadge verification={preview.verification} />
            </div>
            <p className="text-sm text-ink-soft">{preview.verification.summary}</p>
            {preview.verification.source && (
              <p className="mt-2 text-sm">
                <span className="text-ink-soft">Metadata source: </span>
                {preview.verification.source.url ? (
                  <a className="underline" href={preview.verification.source.url} target="_blank" rel="noreferrer">
                    {preview.verification.source.name}
                  </a>
                ) : (
                  preview.verification.source.name
                )}
              </p>
            )}
            <ul className="mt-3 space-y-1 text-sm">
              {preview.verification.checks.map((check) => (
                <li key={check.field} className="flex gap-2">
                  <span aria-hidden className={`w-4 text-center ${check.state === "confirmed" ? "text-emerald-700" : check.state === "missing" ? "text-ink-faint" : "text-amber-700"}`}>
                    {CHECK_MARKS[check.state]}
                  </span>
                  <span>
                    {check.label} <span className="text-ink-faint">· {CHECK_TEXT[check.state]}</span>
                  </span>
                </li>
              ))}
            </ul>
            <label className="mt-3 flex items-start gap-2 border-t border-paper-line pt-3 text-sm">
              <input type="checkbox" className="mt-0.5" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              <span>I have checked this citation against the source myself</span>
            </label>
            <p className="mt-3 text-xs text-ink-faint">{preview.verification.disclaimer}</p>
          </section>
        )}
      </aside>
    </div>
  );
}
