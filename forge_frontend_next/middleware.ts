import { NextRequest, NextResponse } from "next/server";

/**
 * Next.js has trailingSlash=true and skipTrailingSlashRedirect=true because
 * several other backend routes rely on exact paths. Repair ONLY the legacy
 * published-work URLs that were issued without the final slash. Inspect the
 * actual path so an already-canonical URL can never redirect to itself.
 */
export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (/\/practice\/works\/[0-9a-f]{32}$/.test(path)) {
    const canonical = request.nextUrl.clone();
    canonical.pathname = path + "/";
    return NextResponse.redirect(canonical, 307);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/practice/works/:path*"],
};
