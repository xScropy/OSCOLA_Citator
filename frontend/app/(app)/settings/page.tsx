"use client";

import { useState } from "react";
import { useSession } from "@/components/AppShell";
import { ErrorNote, StyleSelect } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";
import { EXPORT_FORMATS } from "@/lib/types";

export default function SettingsPage() {
  const { user, setUser, signOut } = useSession();
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [password, setPassword] = useState("");
  const [deleteError, setDeleteError] = useState("");

  async function update(change: Partial<User>) {
    setSaved(false);
    try {
      setUser(await api<User>("/auth/me", "PATCH", change));
      setError("");
      setSaved(true);
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function deleteAccount(e: React.FormEvent) {
    e.preventDefault();
    if (!window.confirm("Delete your account and every saved reference, note and collection? This cannot be undone.")) return;
    try {
      await api("/auth/me/delete", "POST", { password });
      signOut();
    } catch (err) {
      setDeleteError((err as ApiError).message);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="h1">Settings</h1>

      <section className="card space-y-4 p-4">
        <h2 className="h2">Citation and export preferences</h2>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="default-style" className="text-sm">
            Default citation style
            <span className="block text-xs text-ink-soft">Used for new references, the dashboard and new bibliographies.</span>
          </label>
          <StyleSelect id="default-style" value={user.default_style} onChange={(default_style) => update({ default_style })} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="default-format" className="text-sm">
            Default export format
          </label>
          <select id="default-format" className="input !w-auto" value={user.default_export_format} onChange={(e) => update({ default_export_format: e.target.value })}>
            {EXPORT_FORMATS.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </div>
        {saved && (
          <p role="status" className="text-sm text-emerald-700">
            Preferences saved.
          </p>
        )}
        <ErrorNote>{error}</ErrorNote>
      </section>

      <section className="card space-y-3 p-4">
        <h2 className="h2">Account</h2>
        <p className="text-sm">
          Signed in as <span className="font-medium">{user.email}</span>
        </p>
        <button className="btn" onClick={signOut}>
          Sign out
        </button>
      </section>

      <section className="card border-red-200 p-4">
        <h2 className="h2 !text-red-700">Delete account</h2>
        <p className="mt-1 text-sm text-ink-soft">Permanently removes your account, library, notes and collections from CiteRight.</p>
        <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={deleteAccount}>
          <input type="password" className="input" placeholder="Confirm your password" aria-label="Confirm your password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button className="btn-danger whitespace-nowrap" disabled={!password}>
            Delete my account
          </button>
        </form>
        <div className="mt-2">
          <ErrorNote>{deleteError}</ErrorNote>
        </div>
      </section>
    </div>
  );
}
