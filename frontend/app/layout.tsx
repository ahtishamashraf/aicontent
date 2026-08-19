import type { Metadata, Viewport } from "next";
import { ConfigProvider } from "@/components/config-provider";
import { SessionProvider } from "@/components/session-provider";
import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "OriginLens — signals about how writing was produced",
    template: "%s · OriginLens",
  },
  description:
    "Analyse writing for AI-associated stylistic patterns. Results are estimates with " +
    "stated reliability, never proof of authorship.",
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Never block zoom: pinch-zoom is an accessibility requirement.
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-dvh flex-col">
        <ConfigProvider>
          <SessionProvider>
            <a href="#main" className="skip-link">
              Skip to main content
            </a>
            <SiteNav />
            <main id="main" className="flex-1">
              {children}
            </main>
            <SiteFooter />
          </SessionProvider>
        </ConfigProvider>
      </body>
    </html>
  );
}
