"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, getToken, setToken } from "@/lib/api";
import { ErrorNote } from "@/components/ui";
import type { User } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace("/");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ token: string; user: User }>(`/auth/${mode}`, "POST", { email, password });
      setToken(result.token);
      router.replace("/");
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.status === 422 && mode === "register" && password.length < 8 ? "Choose a password of at least 8 characters." : apiError.message);
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <h1 className="text-center font-serif text-3xl font-semibold text-brand">CiteRight</h1>
        <p className="mt-2 text-center text-sm text-ink-soft">From a case name, ISBN, DOI or URL to a verified citation and an organised research library.</p>
        <form onSubmit={submit} className="card mt-6 space-y-4 p-6">
          <h2 className="text-lg font-semibold">{mode === "login" ? "Sign in" : "Create your account"}</h2>
          <div>
            <label className="label" htmlFor="email">
              Email
            </label>
            <input id="email" type="email" required autoComplete="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="password">
              Password{mode === "register" && " (at least 8 characters)"}
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={mode === "register" ? 8 : undefined}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <ErrorNote>{error}</ErrorNote>
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
          <p className="text-center text-sm text-ink-soft">
            {mode === "login" ? "New to CiteRight?" : "Already have an account?"}{" "}
            <button
              type="button"
              className="font-medium text-brand underline"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
            >
              {mode === "login" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </form>
      </div>
    </main>
  );
}
