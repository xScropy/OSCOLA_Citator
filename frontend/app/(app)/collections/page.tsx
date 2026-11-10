"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Empty, ErrorNote } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Collection } from "@/lib/types";

const SUGGESTIONS = ["International Human Rights Law", "Freedom of Expression", "Right to Privacy", "International Arbitration", "Investment Law", "Moot Court 2026–2027", "Academic Research"];

const GROUPS = [
  { kind: "research", title: "Personal research collections" },
  { kind: "moot", title: "Moot court collections" },
] as const;

export default function CollectionsPage() {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"research" | "moot">("research");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<Collection | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => api<Collection[]>("/collections").then(setCollections).catch((e: ApiError) => setError(e.message)), []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(action: () => Promise<unknown>) {
    try {
      await action();
      setError("");
      await load();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  const unused = SUGGESTIONS.filter((s) => !(collections || []).some((c) => c.name.toLowerCase() === s.toLowerCase()));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">Collections</h1>
        <p className="mt-1 text-sm text-ink-soft">Group authorities by topic, paper or competition. A reference can sit in several collections.</p>
      </div>

      <form
        className="card space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            await api("/collections", "POST", { name, kind, description });
            setName("");
            setDescription("");
          });
        }}
      >
        <h2 className="h2">New collection</h2>
        <div className="grid gap-2 sm:grid-cols-[1fr_12rem_auto]">
          <input className="input" placeholder="Collection name" aria-label="Collection name" value={name} onChange={(e) => setName(e.target.value)} />
          <select className="input" aria-label="Collection kind" value={kind} onChange={(e) => setKind(e.target.value as "research" | "moot")}>
            <option value="research">Personal research</option>
            <option value="moot">Moot court</option>
          </select>
          <button className="btn-primary" disabled={!name.trim()}>
            Create
          </button>
        </div>
        <input className="input" placeholder="Description (optional)" aria-label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        {unused.length > 0 && (
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-ink-soft">
            Suggestions:
            {unused.map((s) => (
              <button
                key={s}
                type="button"
                className="rounded-full border border-paper-line bg-white px-2 py-0.5 hover:border-brand"
                onClick={() => {
                  setName(s);
                  setKind(s.startsWith("Moot") ? "moot" : "research");
                }}
              >
                {s}
              </button>
            ))}
          </p>
        )}
      </form>

      <ErrorNote>{error}</ErrorNote>

      {collections && collections.length === 0 && <Empty title="No collections yet">Create one above, then add references to it from the library.</Empty>}

      {GROUPS.map((group) => {
        const members = (collections || []).filter((c) => c.kind === group.kind);
        if (members.length === 0) return null;
        return (
          <section key={group.kind}>
            <h2 className="h2 mb-3">{group.title}</h2>
            <ul className="grid gap-3 sm:grid-cols-2">
              {members.map((c) => (
                <li key={c.id} className="card p-4">
                  {editing?.id === c.id ? (
                    <form
                      className="space-y-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        act(async () => {
                          await api(`/collections/${c.id}`, "PATCH", { name: editing.name, description: editing.description, kind: editing.kind });
                          setEditing(null);
                        });
                      }}
                    >
                      <input className="input" aria-label="Collection name" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                      <input className="input" aria-label="Description" placeholder="Description" value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
                      <select className="input" aria-label="Collection kind" value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value as "research" | "moot" })}>
                        <option value="research">Personal research</option>
                        <option value="moot">Moot court</option>
                      </select>
                      <div className="flex gap-2">
                        <button className="btn-primary" disabled={!editing.name.trim()}>
                          Save
                        </button>
                        <button type="button" className="btn" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <Link href={`/library?collection_id=${c.id}`} className="font-medium hover:underline">
                        {c.name}
                      </Link>
                      <p className="text-sm text-ink-soft">
                        {c.count} {c.count === 1 ? "reference" : "references"}
                      </p>
                      {c.description && <p className="mt-1 text-sm text-ink-soft">{c.description}</p>}
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Link href={`/library?collection_id=${c.id}`} className="btn !py-1 text-xs">
                          Open
                        </Link>
                        <Link href={`/bibliography?collection_id=${c.id}${c.kind === "moot" ? "&mode=authorities" : ""}`} className="btn !py-1 text-xs">
                          {c.kind === "moot" ? "List of Authorities" : "Bibliography"}
                        </Link>
                        <button className="btn !py-1 text-xs" onClick={() => setEditing(c)}>
                          Edit
                        </button>
                        <button
                          className="btn-danger !py-1 text-xs"
                          onClick={() => {
                            if (window.confirm(`Delete the collection “${c.name}”? Its references stay in your library.`)) act(() => api(`/collections/${c.id}`, "DELETE"));
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
