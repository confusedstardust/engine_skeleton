const rawBasePath = (process.env.NEXT_PUBLIC_BASE_PATH || "").trim();

export const appBasePath =
  !rawBasePath || rawBasePath === "/"
    ? ""
    : `/${rawBasePath.replace(/^\/+|\/+$/g, "")}`;

export function withBasePath(path: string): string {
  if (!path) return appBasePath || "/";
  if (
    path.startsWith("#") ||
    path.startsWith("mailto:") ||
    path.startsWith("tel:") ||
    /^(?:[a-z]+:)?\/\//i.test(path)
  ) {
    return path;
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (!appBasePath) return normalized;
  if (normalized === appBasePath || normalized.startsWith(`${appBasePath}/`)) {
    return normalized;
  }
  return `${appBasePath}${normalized}`;
}

