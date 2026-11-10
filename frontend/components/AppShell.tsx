"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, getToken, setToken } from "@/lib/api";
import type { User } from "@/lib/types";

type Session = { user: User; setUser: (user: User) => void; signOut: () => void };

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside AppShell");
  return session;
}

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/generate", label: "Citation Generator" },
  { href: "/library", label: "My Library" },
  { href: "/collections", label: "Collections" },
  { href: "/bibliography", label: "Bibliography" },
  { href: "/settings", label: "Settings" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");

  const signOut = useCallback(() => {
    setToken(null);
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      .catch((e: ApiError) => {
        if (e.status === 401) signOut();
        else setError(e.message);
      });
  }, [router, signOut]);

  if (error) {
    return (
      <div className="mx-auto mt-24 max-w-md card p-6 text-sm">
        <p className="font-medium">CiteRight could not load.</p>
        <p className="mt-1 text-ink-soft">{error}</p>
        <button className="btn mt-4" onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    );
  }
  if (!user) return <div className="p-10 text-sm text-ink-faint">Loading…</div>;

  return (
    <SessionContext.Provider value={{ user, setUser, signOut }}>
      <div className="min-h-screen md:flex">
        <aside className="border-b border-paper-line bg-brand text-white md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:border-b-0">
          <div className="flex items-center justify-between px-5 py-4 md:block">
            <Link href="/" className="font-serif text-xl font-semibold tracking-tight">
              CiteRight
            </Link>
            <p className="hidden text-xs text-white/60 md:mt-1 md:block">Citations &amp; authorities</p>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:block md:space-y-0.5 md:pb-0">
            {NAV.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`block whitespace-nowrap rounded-md px-3 py-2 text-sm transition ${
                    active ? "bg-white/15 font-medium text-white" : "text-white/75 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="hidden px-5 py-4 text-xs text-white/60 md:absolute md:bottom-0 md:block md:w-56">
            <p className="truncate" title={user.email}>
              {user.email}
            </p>
            <button className="mt-1 underline hover:text-white" onClick={signOut}>
              Sign out
            </button>
          </div>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
          <div className="mx-auto max-w-5xl">{children}</div>
        </main>
      </div>
    </SessionContext.Provider>
  );
}
