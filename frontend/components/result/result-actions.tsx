"use client";

import { useRef, useState } from "react";
import { buildExport } from "@/lib/format";
import type { Analysis } from "@/lib/types";
import { Button } from "@/components/ui/button";

/**
 * Export and print.
 *
 * The download is produced entirely in the browser from data already on screen,
 * so no extra request carries the result anywhere.
 */
export function ResultActions({ analysis }: { analysis: Analysis }) {
  const [copied, setCopied] = useState(false);
  const anchorRef = useRef<HTMLAnchorElement>(null);

  function downloadJson() {
    const blob = new Blob([buildExport(analysis)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = anchorRef.current;
    if (!anchor) return;
    anchor.href = url;
    anchor.download = `originlens-${analysis.id.slice(0, 8)}.json`;
    anchor.click();
    // Revoke on the next tick so the click has already been handled.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="no-print flex flex-wrap items-center gap-2">
      <Button variant="secondary" size="sm" onClick={downloadJson}>
        Download JSON
      </Button>
      <Button variant="secondary" size="sm" onClick={() => window.print()}>
        Print report
      </Button>
      <Button variant="ghost" size="sm" onClick={copyLink}>
        {copied ? "Link copied" : "Copy link"}
      </Button>
      <span aria-live="polite" className="sr-only">
        {copied ? "Link copied to clipboard" : ""}
      </span>
      {/* Hidden anchor drives the download without leaving a stray element visible. */}
      <a ref={anchorRef} className="hidden" aria-hidden="true" tabIndex={-1} href="#">
        download
      </a>
    </div>
  );
}
