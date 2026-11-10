"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "@/components/AppShell";
import { Empty, ErrorNote, Notice, StyleSelect } from "@/components/ui";
import { api, ApiError, copyCitation, download } from "@/lib/api";
import type { Category, Collection, Reference, Section } from "@/lib/types";
import { EXPORT_FORMATS, TYPE_LABELS, TYPE_PLURALS } from "@/lib/types";

type Generated = {
  title: string;
  style: string;
  mode: string;
  sections: Section[];
  needs_attention: { id: number; title: string; missing: string[]; status: string }[];
};

const DEFAULT_CATEGORIES: Category[] = [
  { heading: "Treaties and International Instruments", types: ["treaty"] },
  { heading: "Cases and Judicial Decisions", types: ["case"] },
  { heading: "Legislation", types: ["legislation"] },
  { heading: "Books and Academic Publications", types: ["book", "chapter", "article", "thesis"] },
  { heading: "Other Authorities", types: ["report", "website"] },
];

const DOCUMENT_FORMATS = ["docx", "pdf", "txt"];

/** One bibliography entry the user can edit in place. Edits are kept in `store`, outside React state. */
function EditableEntry({ html, entryKey, store }: { html: string; entryKey: string; store: React.MutableRefObject<Record<string, string>> }) {
  return (
    <p
      className="citation rounded px-2 py-1 pl-8 -indent-6 outline-none hover:bg-paper focus:bg-paper focus:ring-2 focus:ring-brand/20"
      contentEditable
      suppressContentEditableWarning
      spellCheck={false}
      aria-label="Bibliography entry (editable)"
      dangerouslySetInnerHTML={{ __html: html }}
      onInput={(e) => {
        store.current[entryKey] = e.currentTarget.innerHTML;
      }}
      onPaste={(e) => {
        e.preventDefault();
        document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
      }}
    />
  );
}

export default function BibliographyPage() {
  const { user } = useSession();
  const params = useSearchParams();
  const [references, setReferences] = useState<Reference[] | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [style, setStyle] = useState(user.default_style);
  const [mode, setMode] = useState<"bibliography" | "authorities">(params.get("mode") === "authorities" ? "authorities" : "bibliography");
  const [categories, setCategories] = useState<Category[]>(DEFAULT_CATEGORIES);
  const [generated, setGenerated] = useState<Generated | null>(null);
  const [generation, setGeneration] = useState(0);
  const [title, setTitle] = useState("");
  const [format, setFormat] = useState(user.default_export_format);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const edits = useRef<Record<string, string>>({});

  useEffect(() => {
    const collectionId = params.get("collection_id");
    const ids = (params.get("ids") || "").split(",").map(Number).filter(Boolean);
    Promise.all([api<{ items: Reference[] }>("/references?sort=author"), api<Collection[]>("/collections")])
      .then(([list, cols]) => {
        setReferences(list.items);
        setCollections(cols);
        if (ids.length) setSelected(list.items.filter((r) => ids.includes(r.id)).map((r) => r.id));
        else if (collectionId) setSelected(list.items.filter((r) => r.collection_ids.includes(Number(collectionId))).map((r) => r.id));
        else setSelected(list.items.map((r) => r.id));
      })
      .catch((e: ApiError) => setError(e.message));
  }, [params]);

  const request = useMemo(
    () => ({ reference_ids: selected, style, mode, categories: mode === "authorities" ? categories.filter((c) => c.heading.trim() && c.types.length) : null }),
    [selected, style, mode, categories],
  );

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const result = await api<Generated>("/bibliography", "POST", request);
      edits.current = {};
      setGenerated(result);
      setTitle(result.title);
      setGeneration((n) => n + 1);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  /** The list as it currently stands on screen, including the user's edits. */
  function currentSections(): Section[] {
    return (generated?.sections || []).map((section, s) => ({
      heading: section.heading,
      entries: section.entries.map((entry, e) => ({ ...entry, html: edits.current[`${s}-${e}`] ?? entry.html })),
    }));
  }

  function mutate(change: (sections: Section[]) => Section[]) {
    if (!generated) return;
    const next = change(currentSections()).filter((s) => s.entries.length > 0);
    edits.current = {};
    setGenerated({ ...generated, sections: next });
    setGeneration((n) => n + 1);
  }

  async function exportFile() {
    setError("");
    try {
      const body = DOCUMENT_FORMATS.includes(format) && generated ? { ...request, format, title, sections: currentSections() } : { ...request, format, title: title || null };
      await download("/export", body);
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function copyAll() {
    const sections = currentSections();
    const html = sections.map((s) => (s.heading ? `<p><b>${s.heading.replace(/[<>&]/g, "")}</b></p>` : "") + s.entries.map((e) => `<p>${e.html}</p>`).join("")).join("");
    const holder = document.createElement("div");
    holder.innerHTML = sections.map((s) => (s.heading ? `<p>${s.heading.replace(/[<>&]/g, "")}</p>` : "") + s.entries.map((e) => `<p>${e.html}</p>`).join("")).join("");
    const text = Array.from(holder.querySelectorAll("p")).map((p) => p.textContent || "").join("\n");
    setCopied(await copyCitation(text, html));
    window.setTimeout(() => setCopied(false), 1600);
  }

  const toggleType = (index: number, type: string) =>
    setCategories(
      categories.map((c, i) =>
        i === index ? { ...c, types: c.types.includes(type) ? c.types.filter((t) => t !== type) : [...c.types, type] } : { ...c, types: c.types.filter((t) => t !== type) },
      ),
    );
  const move = (index: number, delta: number) => {
    const next = [...categories];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    setCategories(next);
  };

  if (references && references.length === 0) {
    return (
      <div className="space-y-5">
        <h1 className="h1">Bibliography</h1>
        <Empty title="Your library is empty">
          <Link className="underline" href="/generate">
            Add some sources
          </Link>{" "}
          first, then come back to build a bibliography or List of Authorities.
        </Empty>
      </div>
    );
  }

  const isDocument = DOCUMENT_FORMATS.includes(format);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">Bibliography</h1>
        <p className="mt-1 text-sm text-ink-soft">Build a bibliography or a moot-court List of Authorities from your saved references, edit it, then export.</p>
      </div>

      <section className="card space-y-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex overflow-hidden rounded-md border border-paper-line">
            {(["bibliography", "authorities"] as const).map((m) => (
              <button key={m} className={`px-3 py-1.5 text-sm ${mode === m ? "bg-brand text-white" : "bg-white text-ink hover:bg-paper"}`} aria-pressed={mode === m} onClick={() => setMode(m)}>
                {m === "bibliography" ? "Bibliography" : "List of Authorities"}
              </button>
            ))}
          </div>
          <StyleSelect value={style} onChange={setStyle} />
        </div>

        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">
              {selected.length} of {references?.length ?? 0} references selected
            </span>
            <button className="btn !py-1 text-xs" onClick={() => setSelected((references || []).map((r) => r.id))}>
              Select all
            </button>
            <button className="btn !py-1 text-xs" onClick={() => setSelected([])}>
              Clear
            </button>
            {collections.length > 0 && (
              <select
                className="input !w-auto !py-1 text-xs"
                aria-label="Select a collection"
                value=""
                onChange={(e) => e.target.value && setSelected((references || []).filter((r) => r.collection_ids.includes(Number(e.target.value))).map((r) => r.id))}
              >
                <option value="">Select a collection…</option>
                {collections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.count})
                  </option>
                ))}
              </select>
            )}
          </div>
          <ul className="max-h-64 divide-y divide-paper-line overflow-y-auto rounded-md border border-paper-line">
            {(references || []).map((r) => (
              <li key={r.id}>
                <label className="flex cursor-pointer items-start gap-2 px-3 py-2 text-sm hover:bg-paper">
                  <input type="checkbox" className="mt-1" checked={selected.includes(r.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, r.id] : selected.filter((id) => id !== r.id))} />
                  <span className="min-w-0">
                    <span className="break-words">{String(r.metadata.title)}</span>
                    <span className="ml-2 text-xs text-ink-faint">{TYPE_LABELS[r.type]}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>

        {mode === "authorities" && (
          <div>
            <h2 className="h2 mb-1">Categories</h2>
            <p className="mb-2 text-xs text-ink-soft">Rename, reorder or regroup to match your competition’s rules. Each source type belongs to one category.</p>
            <ul className="space-y-2">
              {categories.map((category, index) => (
                <li key={index} className="rounded-md border border-paper-line p-2">
                  <div className="flex gap-2">
                    <input className="input" aria-label={`Category ${index + 1} heading`} value={category.heading} onChange={(e) => setCategories(categories.map((c, i) => (i === index ? { ...c, heading: e.target.value } : c)))} />
                    <button className="btn !px-2" aria-label="Move up" disabled={index === 0} onClick={() => move(index, -1)}>
                      ↑
                    </button>
                    <button className="btn !px-2" aria-label="Move down" disabled={index === categories.length - 1} onClick={() => move(index, 1)}>
                      ↓
                    </button>
                    <button className="btn !px-2" aria-label="Remove category" onClick={() => setCategories(categories.filter((_, i) => i !== index))}>
                      ✕
                    </button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {Object.keys(TYPE_PLURALS).map((type) => (
                      <button
                        key={type}
                        aria-pressed={category.types.includes(type)}
                        onClick={() => toggleType(index, type)}
                        className={`rounded-full border px-2 py-0.5 text-xs ${category.types.includes(type) ? "border-brand bg-brand-tint text-brand" : "border-paper-line bg-white text-ink-faint hover:text-ink"}`}
                      >
                        {TYPE_PLURALS[type]}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex gap-2">
              <button className="btn !py-1 text-xs" onClick={() => setCategories([...categories, { heading: "New category", types: [] }])}>
                + Add category
              </button>
              <button className="btn !py-1 text-xs" onClick={() => setCategories(DEFAULT_CATEGORIES)}>
                Reset to defaults
              </button>
            </div>
          </div>
        )}

        <button className="btn-primary" disabled={busy || selected.length === 0} onClick={generate}>
          {busy ? "Generating…" : generated ? "Regenerate" : mode === "authorities" ? "Generate List of Authorities" : "Generate bibliography"}
        </button>
        {generated && <p className="text-xs text-ink-faint">Regenerating replaces any manual edits below.</p>}
      </section>

      <ErrorNote>{error}</ErrorNote>

      {generated && (
        <>
          {generated.needs_attention.length > 0 && (
            <Notice>
              <p className="font-medium">
                {generated.needs_attention.length} {generated.needs_attention.length === 1 ? "entry needs" : "entries need"} attention before you rely on this list
              </p>
              <ul className="mt-1 list-disc pl-5">
                {generated.needs_attention.map((item) => (
                  <li key={item.id}>
                    <Link className="underline" href={`/library/${item.id}`}>
                      {item.title}
                    </Link>
                    {item.missing.length > 0 ? ` · missing ${item.missing.join(", ")}` : " · not verified against a source"}
                  </li>
                ))}
              </ul>
            </Notice>
          )}

          <section className="card p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-paper-line pb-4">
              <p className="text-sm text-ink-soft">Click any entry to edit it before exporting.</p>
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn" onClick={copyAll}>
                  {copied ? "Copied" : "Copy all"}
                </button>
                <select className="input !w-auto" aria-label="Export format" value={format} onChange={(e) => setFormat(e.target.value)}>
                  {EXPORT_FORMATS.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </select>
                <button className="btn-primary" onClick={exportFile}>
                  Export
                </button>
              </div>
            </div>
            {!isDocument && <p className="mb-3 text-xs text-ink-faint">This format exports the reference data of the selected sources. Manual edits to entries apply to Word, PDF and text exports only.</p>}
            <input className="mb-4 w-full border-0 bg-transparent font-serif text-2xl font-semibold outline-none focus:ring-0" aria-label="Document title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <div key={generation} className="space-y-5">
              {generated.sections.map((section, s) => (
                <div key={s}>
                  {(section.heading || generated.sections.length > 1) && (
                    <input
                      className="mb-1 w-full border-0 bg-transparent px-2 text-sm font-semibold uppercase tracking-wide text-ink-soft outline-none"
                      aria-label="Section heading"
                      defaultValue={section.heading}
                      onBlur={(e) => {
                        const heading = e.target.value;
                        if (heading !== section.heading) mutate((sections) => sections.map((sec, i) => (i === s ? { ...sec, heading } : sec)));
                      }}
                    />
                  )}
                  {section.entries.map((entry, e) => (
                    <div key={e} className="group flex items-start gap-1">
                      <div className="min-w-0 flex-1">
                        <EditableEntry html={entry.html} entryKey={`${s}-${e}`} store={edits} />
                      </div>
                      <button
                        className="mt-1 rounded px-1.5 text-xs text-ink-faint opacity-0 hover:text-red-700 focus:opacity-100 group-hover:opacity-100"
                        aria-label="Remove entry from this list"
                        onClick={() => mutate((sections) => sections.map((sec, i) => (i === s ? { ...sec, entries: sec.entries.filter((_, j) => j !== e) } : sec)))}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
