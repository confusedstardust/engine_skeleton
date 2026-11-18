/** Informational marker only. Never treat this as iframe permission authorization. */
export function supportsGestureBridge(html:string):boolean {
  return /<body\b[^>]*\bdata-nar-gesture\s*=\s*(?:["']v1["']|v1(?=\s|>))/i.test(html);
}
