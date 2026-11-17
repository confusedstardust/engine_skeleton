import { NextRequest, NextResponse } from "next/server";
import { portalHref } from "@narrativeos/ui/app-links";

/**
 * Next.js has trailingSlash=true and skipTrailingSlashRedirect=true because
 * several other backend routes rely on exact paths. Repair ONLY the legacy
 * published-work URLs that were issued without the final slash. Inspect the
 * actual path so an already-canonical URL can never redirect to itself.
 * The separate support embed is restricted to Forge and its matching portal.
 */
export function middleware(request: NextRequest) {
  // NextURL.pathname can normalize away the slash under skipTrailingSlashRedirect.
  // The raw incoming request path is the only reliable distinction.
  const canonical = new URL(request.url);
  const path = canonical.pathname;
  if (/\/support\/embed\/?$/.test(path)) {
    // Next can use the listener's hostname in request.url, so use the public Host for the sibling port.
    const origin = new URL(canonical.origin);
    const host = request.headers.get("host");
    if (host) origin.host = host;
    const portal = portalHref("/", origin.origin, process.env.NEXT_PUBLIC_SSO_ORIGIN);
    const response = NextResponse.next();
    response.headers.set("Content-Security-Policy", `frame-ancestors 'self' ${new URL(portal, origin).origin}`);
    return response;
  }
  if (/\/practice\/works\/[0-9a-f]{32}$/.test(path)) {
    canonical.pathname = path + "/";
    return NextResponse.redirect(canonical, 307);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/practice/works/:path*", "/support/embed"],
};
