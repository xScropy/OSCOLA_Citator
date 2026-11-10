"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "@/components/AppShell";
import ReferenceCard from "@/components/ReferenceCard";
import { CitationText, Empty, ErrorNote, StyleSelect } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Collection, Reference } from "@/lib/types";
import { TYPE_PLURALS } from "@/lib/types";

type Listing = { total: number; count: number; tags: string[]; items: Reference[] };
type DuplicateGroup = { reasons: string[]; items: Reference[] };

const TABS = ["", "case", "book", "article", "treaty", "legislation", "report", "chapter", "thesis", "website"];

export default function LibraryPage() {
  const { user } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState("");
  const [type, setType] = useState(params.get("type") || "");
  const [category] = useState(params.get("category") || "");
  const [tag, setTag] = useState("");
  const [collectionId, setCollectionId] = useState(params.get("collection_id") || "");
  const [verification, setVerification] = useState(params.get("verification") || "");
  const [preferredStyle, setPreferredStyle] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [sort, setSort] = useState("added");
  const [style, setStyle] = useState(user.default_style);
  const [listing, setListing] = useState<Listing | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const query = new URLSearchParams({ sort, style });
    if (q.trim()) query.set("q", q.trim());
    if (type) query.set("type", type);
    if (category) query.set("category", category);
    if (tag) query.set("tag", tag);
    if (collectionId) query.set("collection_id", collectionId);
    if (verification) query.set("verification", verification);
    if (preferredStyle) query.set("preferred_style", preferredStyle);
    if (favorite) query.set("favorite", "true");
    try {
      const [items, dupes] = await Promise.all([api<Listing>(`/references?${query}`), api<{ groups: DuplicateGroup[] }>("/references/duplicates")]);
      setListing(items);
      setGroups(dupes.groups);
      setError("");
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, [q, type, category, tag, collectionId, verification, preferredStyle, favorite, sort, style]);

  useEffect(() => {
    const timer = window.setTimeout(load, q ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, q]);

  useEffect(() => {
    api<Collection[]>("/collections").then(setCollections).catch(() => setCollections([]));
  }, []);

  async function act(action: () => Promise<unknown>) {
    try {
      await action();
      await load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  const toggleFavorite = (r: Reference) => act(() => api(`/references/${r.id}`, "PATCH", { favorite: !r.favorite }));
  const remove = (r: Reference) => {
    if (!window.confirm(`Delete “${r.metadata.title}” from your library? This cannot be undone.`)) return;
    setSelected((ids) => ids.filter((id) => id !== r.id));
    act(() => api(`/references/${r.id}`, "DELETE"));
  };
  const merge = (keep: Reference, other: Reference) => {
    if (!window.confirm(`Merge into “${keep.metadata.title}”? Its details are kept, gaps are filled from the other entry, and the other entry is removed.`)) return;
    act(() => api(`/references/${keep.id}/merge`, "POST", { source_id: other.id }));
  };

  const items = listing?.items || [];
  const allSelected = items.length > 0 && items.every((r) => selected.includes(r.id));
  const activeCollection = collections.find((c) => String(c.id) === collectionId);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h1">My Library</h1>
          <p className="mt-1 text-sm text-ink-soft">
            {listing ? `${listing.count} of ${listing.total} references` : "Loading…"}
            {category && ` · ${category === "legal" ? "legal authorities" : "academic publications"}`}
            {activeCollection && ` · in “${activeCollection.name}”`}
          </p>
        </div>
        <Link href="/generate" className="btn-primary">
          Add a source
        </Link>
      </div>

      {groups.length > 0 && (
        <section className="card border-amber-300 bg-amber-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">
              {groups.length} possible duplicate {groups.length === 1 ? "group" : "groups"} in your library
            </p>
            <button className="btn" onClick={() => setShowDuplicates(!showDuplicates)}>
              {showDuplicates ? "Hide" : "Review"}
            </button>
          </div>
          {showDuplicates && (
            <div className="mt-3 space-y-3">
              {groups.map((group, index) => (
                <div key={index} className="rounded-md border border-amber-200 bg-white p-3">
                  <p className="mb-2 text-xs text-ink-soft">{group.reasons.join(" · ")}</p>
                  <ul className="space-y-2">
                    {group.items.map((item) => (
                      <li key={item.id} className="flex flex-wrap items-start justify-between gap-2 text-sm">
                        <Link href={`/library/${item.id}`} className="min-w-0 flex-1 hover:underline">
                          <CitationText form={item.citations.forms.full} />
                        </Link>
                        <div className="flex gap-1">
                          {group.items
                            .filter((other) => other.id !== item.id)
                            .map((other) => (
                              <button key={other.id} className="btn !px-2 !py-1 text-xs" onClick={() => merge(item, other)}>
                                Keep this{group.items.length > 2 ? `, merge #${group.items.indexOf(other) + 1}` : ", merge the other"}
                              </button>
                            ))}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              <p className="text-xs text-ink-soft">Different editions or separate judgments with the same name are not duplicates. Leave them as they are.</p>
            </div>
          )}
        </section>
      )}

      <div className="flex gap-1 overflow-x-auto border-b border-paper-line">
        {TABS.map((id) => (
          <button
            key={id}
            onClick={() => setType(id)}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm ${type === id ? "border-brand font-medium text-brand" : "border-transparent text-ink-soft hover:text-ink"}`}
          >
            {id ? TYPE_PLURALS[id] : "All references"}
          </button>
        ))}
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <input className="input lg:col-span-2" placeholder="Search titles, authors, citations, notes, tags" aria-label="Search library" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input" aria-label="Sort by" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="added">Sort: recently added</option>
          <option value="author">Sort: author</option>
          <option value="title">Sort: title</option>
          <option value="date">Sort: date (newest)</option>
        </select>
        <select className="input" aria-label="Filter by verification" value={verification} onChange={(e) => setVerification(e.target.value)}>
          <option value="">Any verification status</option>
          <option value="verified">Verified</option>
          <option value="partially_verified">Partially Verified</option>
          <option value="user_confirmed">User Confirmed</option>
          <option value="needs_review">Needs Review</option>
        </select>
        <select className="input" aria-label="Filter by collection" value={collectionId} onChange={(e) => setCollectionId(e.target.value)}>
          <option value="">All collections</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select className="input" aria-label="Filter by tag" value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">All tags</option>
          {(listing?.tags || []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select className="input" aria-label="Filter by saved citation style" value={preferredStyle} onChange={(e) => setPreferredStyle(e.target.value)}>
          <option value="">Saved in any style</option>
          <option value="oscola">Saved as OSCOLA</option>
          <option value="bluebook">Saved as Bluebook</option>
          <option value="apa">Saved as APA</option>
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={favorite} onChange={(e) => setFavorite(e.target.checked)} />
          Favourites only
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={allSelected}
            disabled={items.length === 0}
            onChange={(e) => setSelected(e.target.checked ? Array.from(new Set([...selected, ...items.map((r) => r.id)])) : selected.filter((id) => !items.some((r) => r.id === id)))}
          />
          Select all shown
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-ink-soft">Show as</span>
          <StyleSelect value={style} onChange={setStyle} />
          <button className="btn-primary" disabled={selected.length === 0} onClick={() => router.push(`/bibliography?ids=${selected.join(",")}`)}>
            Generate bibliography{selected.length > 0 && ` (${selected.length})`}
          </button>
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {listing && items.length === 0 ? (
        listing.total === 0 ? (
          <Empty title="No references yet">
            <Link className="underline" href="/generate">
              Find your first source
            </Link>{" "}
            by case name, ISBN, DOI, title or URL.
          </Empty>
        ) : (
          <Empty title="Nothing matches these filters">Clear the search or choose a different filter.</Empty>
        )
      ) : (
        <ul className="space-y-3">
          {items.map((r) => (
            <ReferenceCard
              key={r.id}
              reference={r}
              selected={selected.includes(r.id)}
              onSelect={(on) => setSelected(on ? [...selected, r.id] : selected.filter((id) => id !== r.id))}
              onFavorite={() => toggleFavorite(r)}
              onDelete={() => remove(r)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
