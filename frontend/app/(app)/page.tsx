"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ReferenceCard from "@/components/ReferenceCard";
import { Empty, ErrorNote } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Stats } from "@/lib/types";

const STATUSES = [
  { id: "verified", label: "Verified", bar: "bg-emerald-600" },
  { id: "partially_verified", label: "Partially Verified", bar: "bg-amber-500" },
  { id: "user_confirmed", label: "User Confirmed", bar: "bg-sky-600" },
  { id: "needs_review", label: "Needs Review", bar: "bg-red-500" },
];

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api<Stats>("/stats").then(setStats).catch((e: ApiError) => setError(e.message));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="h1">Dashboard</h1>
        <p className="mt-1 text-sm text-ink-soft">Stop formatting citations manually. Focus on the quality of your legal research.</p>
      </div>

      <form
        className="card flex flex-col gap-2 p-4 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim()) router.push(`/generate?q=${encodeURIComponent(query.trim())}`);
        }}
      >
        <input
          className="input !py-2.5 !text-base"
          placeholder="Enter a case name, ISBN, DOI, title or URL"
          aria-label="Find a source"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn-primary !px-5" disabled={!query.trim()}>
          Find source
        </button>
      </form>

      <ErrorNote>{error}</ErrorNote>

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              { label: "Saved references", value: stats.total, href: "/library" },
              { label: "Legal authorities", value: stats.legal, href: "/library?category=legal" },
              { label: "Academic publications", value: stats.academic, href: "/library?category=academic" },
              { label: "Collections", value: stats.collections, href: "/collections" },
            ].map((item) => (
              <Link key={item.label} href={item.href} className="card p-4 transition hover:border-brand">
                <p className="text-3xl font-semibold tabular-nums">{item.value}</p>
                <p className="mt-1 text-sm text-ink-soft">{item.label}</p>
              </Link>
            ))}
          </div>

          {stats.total > 0 && (
            <section className="card p-4">
              <h2 className="h2 mb-3">Citation verification</h2>
              <div className="flex h-2 overflow-hidden rounded-full bg-paper">
                {STATUSES.map((s) => (
                  <div key={s.id} className={s.bar} style={{ width: `${(100 * (stats.verification[s.id] || 0)) / stats.total}%` }} />
                ))}
              </div>
              <ul className="mt-3 grid grid-cols-2 gap-2 text-sm lg:grid-cols-4">
                {STATUSES.map((s) => (
                  <li key={s.id}>
                    <Link href={`/library?verification=${s.id}`} className="flex items-center gap-2 hover:underline">
                      <span className={`h-2.5 w-2.5 rounded-full ${s.bar}`} />
                      <span className="font-medium tabular-nums">{stats.verification[s.id] || 0}</span>
                      <span className="text-ink-soft">{s.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {stats.total === 0 ? (
            <Empty title="Your library is empty">
              Search for a source above, or <Link className="underline" href="/generate?manual=1">enter one manually</Link>.
            </Empty>
          ) : (
            <div className="grid gap-8 lg:grid-cols-2">
              <section>
                <h2 className="h2 mb-3">Recently added</h2>
                <ul className="space-y-3">
                  {stats.recent.map((r) => (
                    <ReferenceCard key={r.id} reference={r} />
                  ))}
                </ul>
              </section>
              <section>
                <h2 className="h2 mb-3">Favourite authorities</h2>
                {stats.favorites.length === 0 ? (
                  <p className="text-sm text-ink-soft">Star a reference in your library to keep it here.</p>
                ) : (
                  <ul className="space-y-3">
                    {stats.favorites.map((r) => (
                      <ReferenceCard key={r.id} reference={r} />
                    ))}
                  </ul>
                )}
              </section>
            </div>
          )}
        </>
      )}
    </div>
  );
}
