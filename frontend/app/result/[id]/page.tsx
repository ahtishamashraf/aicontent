import type { Metadata } from "next";
import { ResultView } from "@/components/result/result-view";

export const metadata: Metadata = {
  title: "Result",
  description: "Analysis result with reliability, paragraph breakdown, and disclaimers.",
};

export default async function ResultPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ResultView analysisId={id} />;
}
