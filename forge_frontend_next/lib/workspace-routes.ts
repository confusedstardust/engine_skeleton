export function agentRoute(path: string) {
  return path === "/practice" || /^\/practice\/chat\/[a-f0-9]{32}$/.test(path);
}
