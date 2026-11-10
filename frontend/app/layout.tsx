import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CiteRight",
  description: "Legal citation and authority management: OSCOLA, Bluebook and APA.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
