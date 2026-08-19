import type { Metadata } from "next";
import { Analyzer } from "@/components/analyzer";

export const metadata: Metadata = {
  title: "Analyze",
  description: "Submit writing or a document for analysis.",
};

export default function AnalyzePage() {
  return (
    <div className="container-page max-w-3xl py-10 sm:py-14">
      <h1 className="text-3xl font-bold text-ink">Analyze writing</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Paste text or upload a document. The result reports a band and a reliability level,
        with the reasons for both.
      </p>
      <div className="mt-8">
        <Analyzer />
      </div>
    </div>
  );
}
