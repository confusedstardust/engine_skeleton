import { NextRequest, NextResponse } from "next/server";

const allowed = new Set(["login", "register", "email/send-code", "email/verify"]);

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!allowed.has(path)) return NextResponse.json({ error: "接口不存在" }, { status: 404 });
  if (request.headers.get("x-forge-auth-action") !== "1") return NextResponse.json({ error: "无效登录请求" }, { status: 403 });
  // Only configured origins or the known local SSO service may receive credentials.
  const local = process.env.NODE_ENV === "development" && ["localhost", "127.0.0.1"].includes(request.nextUrl.hostname);
  const origin = process.env.FORGE_SSO_ORIGIN || process.env.NEXT_PUBLIC_SSO_ORIGIN || (local ? `http://${request.nextUrl.hostname}:3000` : "https://www.narrativeos.cn");
  const body = await request.text();
  if (body.length > 16384) return NextResponse.json({ error: "请求内容过长" }, { status: 413 });
  try {
    const upstream = await fetch(new URL(`/api/auth/${path}`, origin), {
      method: "POST", headers: { "Content-Type": "application/json" }, body,
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(15000),
    });
    const response = new NextResponse(await upstream.text(), { status: upstream.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
    for (const cookie of upstream.headers.getSetCookie()) response.headers.append("Set-Cookie", cookie);
    return response;
  } catch {
    return NextResponse.json({ error: "登录服务暂时不可用，请稍后重试" }, { status: 503 });
  }
}
