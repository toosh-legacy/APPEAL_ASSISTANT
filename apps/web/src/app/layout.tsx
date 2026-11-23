import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import Providers from "@/components/Providers";

export const metadata: Metadata = {
  title: "Appeal Assistant",
  description: "Understand a health insurance denial and draft a cited appeal letter.",
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 bg-white p-2">
          Skip to main content
        </a>
        <header className="border-b border-slate-200 bg-white">
          <nav aria-label="Main" className="mx-auto flex max-w-3xl items-center justify-between px-4 py-1">
            <Link href="/" className="inline-flex min-h-11 items-center font-bold text-slate-900 no-underline">
              Appeal Assistant
            </Link>
            <div className="flex gap-2 text-sm sm:gap-4">
              <Link href="/start" className="inline-flex min-h-11 items-center px-1">
                Start
              </Link>
              <Link href="/insights/insurers" className="inline-flex min-h-11 items-center px-1">
                Insurers
              </Link>
              <Link href="/about/data" className="inline-flex min-h-11 items-center px-1">
                Data &amp; sources
              </Link>
            </div>
          </nav>
        </header>
        <main id="main" className="mx-auto max-w-3xl px-4 py-6">
          <Providers>{children}</Providers>
        </main>
        <footer className="mx-auto max-w-3xl px-4 pb-10 text-sm text-slate-700">
          <p>
            Not legal or medical advice. You are the author of your appeal. IMR data: California Department of Managed Health Care (CC BY). Regulations: eCFR.
          </p>
        </footer>
      </body>
    </html>
  );
}
