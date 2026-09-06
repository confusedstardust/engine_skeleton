import { NextResponse } from "next/server";

const backend = process.env.FORGE_BACKEND_URL || "http://127.0.0.1:8010";
const safeAssetName = /^[A-Za-z0-9_-]+\.(?:png|webp)$/i;

export async function GET(_request: Request, context: { params: Promise<{ assetName: string }> }) {
  const { assetName } = await context.params;
  if (!safeAssetName.test(assetName)) {
    return NextResponse.json({ detail: "particle effect asset not found" }, { status: 404 });
  }
  const response = await fetch(`${backend}/effect-library/${encodeURIComponent(assetName)}`, { cache: "no-store" });
  if (!response.ok) {
    return NextResponse.json({ detail: "particle effect asset not found" }, { status: response.status });
  }
  return new NextResponse(await response.arrayBuffer(), {
    headers: {
      "Content-Type": assetName.toLowerCase().endsWith(".webp") ? "image/webp" : "image/png",
      "Cache-Control": "public, max-age=3600"
    }
  });
}
