import {BRIDGE_BOOTSTRAP} from "./bridge-bootstrap";
export const WORK_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; media-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";
/** DOMParser is an inert HTML5 parser; do not inject the generated HTML into the parent DOM. */
export function buildPreviewHTML(html:string,parentOrigin:string):string{
  const documentNode=new DOMParser().parseFromString(html,"text/html");
  const csp=documentNode.createElement("meta");
  csp.setAttribute("http-equiv","Content-Security-Policy");csp.setAttribute("content",WORK_CSP);
  const referrer=documentNode.createElement("meta");
  referrer.setAttribute("name","referrer");referrer.setAttribute("content","no-referrer");
  const bootstrap=documentNode.createElement("script");
  bootstrap.setAttribute("data-parent-origin",parentOrigin);
  bootstrap.textContent=BRIDGE_BOOTSTRAP;
  // Always first: the policy must precede the bootstrap and all work scripts.
  documentNode.head.insertBefore(referrer,documentNode.head.firstChild);
  documentNode.head.insertBefore(bootstrap,documentNode.head.firstChild);
  documentNode.head.insertBefore(csp,documentNode.head.firstChild);
  return "<!doctype html>\n"+documentNode.documentElement.outerHTML;
}
