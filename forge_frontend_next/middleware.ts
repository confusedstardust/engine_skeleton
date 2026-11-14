import { NextRequest, NextResponse } from "next/server";

/**
 * Next.js has trailingSlash=true and skipTrailingSlashRedirect=true because
 * several other backend routes rely on exact paths. Repair ONLY the legacy
 * published-work URLs that were issued without the final slash. Inspect the
 * actual path so an already-canonical URL can never redirect to itself.
 */
export function middleware(request: NextRequest) {
  // NextURL.pathname can normalize away the slash under skipTrailingSlashRedirect.
  // The raw incoming request path is the only reliable distinction.
  const canonical = new URL(request.url);
  const path = canonical.pathname;
  if (/\/practice\/works\/[0-9a-f]{32}$/.test(path)) {
    canonical.pathname = path + "/";
    return NextResponse.redirect(canonical, 307);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/practice/works/:path*"],
};
