import { Suspense } from "react";
import AppShell from "@/components/AppShell";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <Suspense fallback={<p className="text-sm text-ink-faint">Loading…</p>}>{children}</Suspense>
    </AppShell>
  );
}
