"use client";

import Link from "next/link";
import type { Reference } from "@/lib/types";
import { TYPE_LABELS } from "@/lib/types";
import { CitationText, CopyButton, StatusBadge } from "./ui";

export default function ReferenceCard({
  reference,
  selected,
  onSelect,
  onFavorite,
  onDelete,
}: {
  reference: Reference;
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
  onFavorite?: () => void;
  onDelete?: () => void;
}) {
  const form = reference.citations.forms.full;
  const missing = reference.citations.missing.required;
  return (
    <li className="card flex gap-3 p-4">
      {onSelect && (
        <input type="checkbox" className="mt-1.5" checked={!!selected} onChange={(e) => onSelect(e.target.checked)} aria-label={`Select ${reference.metadata.title}`} />
      )}
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
          <span className="font-medium uppercase tracking-wide">{TYPE_LABELS[reference.type] || reference.type}</span>
          <StatusBadge verification={reference.verification} />
          {reference.tags.map((tag) => (
            <span key={tag} className="rounded-full bg-brand-tint px-2 py-0.5 text-brand">
              {tag}
            </span>
          ))}
        </div>
        <p>
          <CitationText form={form} />
        </p>
        {missing.length > 0 && <p className="mt-1 text-xs text-amber-800">Missing: {missing.join(", ")}</p>}
        {reference.notes && <p className="mt-1.5 line-clamp-2 whitespace-pre-line text-sm text-ink-soft">{reference.notes}</p>}
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <CopyButton form={form} />
          <Link href={`/library/${reference.id}`} className="btn !px-2 !py-1 text-xs">
            Open
          </Link>
          {onDelete && (
            <button className="btn-danger !px-2 !py-1 text-xs" onClick={onDelete}>
              Delete
            </button>
          )}
        </div>
      </div>
      {onFavorite && (
        <button
          className={`h-8 shrink-0 text-xl leading-none ${reference.favorite ? "text-accent" : "text-ink-faint hover:text-accent"}`}
          aria-label={reference.favorite ? "Remove from favourites" : "Add to favourites"}
          aria-pressed={reference.favorite}
          onClick={onFavorite}
        >
          {reference.favorite ? "★" : "☆"}
        </button>
      )}
    </li>
  );
}
