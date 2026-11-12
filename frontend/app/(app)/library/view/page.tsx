"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import ReferenceEditor from "@/components/ReferenceEditor";
import { ErrorNote } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Reference } from "@/lib/types";

export default function ReferencePage() {
  const id = useSearchParams().get("id");
  const router = useRouter();
  const [reference, setReference] = useState<Reference | null>(null);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState(0);

  useEffect(() => {
    if (!id || !/^\d+$/.test(id)) {
      setError("This reference is no longer in your library.");
      return;
    }
    api<Reference>(`/references/${id}`)
      .then(setReference)
      .catch((e: ApiError) => setError(e.status === 404 ? "This reference is no longer in your library." : e.message));
  }, [id]);

  async function remove() {
    if (!reference || !window.confirm(`Delete “${reference.metadata.title}” from your library? This cannot be undone.`)) return;
    try {
      await api(`/references/${reference.id}`, "DELETE");
      router.replace("/library");
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href="/library" className="text-sm text-ink-soft underline">
            ← My Library
          </Link>
          <h1 className="h1 mt-2 break-words">{reference ? String(reference.metadata.title) : "Reference"}</h1>
          {savedAt > 0 && (
            <p role="status" className="mt-1 text-sm text-emerald-700">
              Changes saved.
            </p>
          )}
        </div>
        {reference && (
          <button className="btn-danger" onClick={remove}>
            Delete reference
          </button>
        )}
      </div>
      <ErrorNote>{error}</ErrorNote>
      {reference && (
        <ReferenceEditor
          key={`${reference.id}-${savedAt}`}
          draft={{
            id: reference.id,
            metadata: reference.metadata,
            retrieved: reference.retrieved,
            source: reference.source,
            pinpoint: reference.pinpoint,
            style: reference.style,
            notes: reference.notes,
            tags: reference.tags,
            favorite: reference.favorite,
            user_confirmed: reference.user_confirmed,
            collection_ids: reference.collection_ids,
          }}
          onSaved={(ref) => {
            setReference(ref);
            setSavedAt(Date.now());
          }}
        />
      )}
    </div>
  );
}
