"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState, type MouseEvent } from "react";
import { withBasePath } from "../app/base-path";
import { ssoLoginUrl } from "../app/invite-identity";
import { useAnnouncements } from "./announcements";

export default function SiteFooter() {
  const openAnnouncements = useAnnouncements();
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const [casesHref, setCasesHref] = useState("https://www.narrativeos.cn/#cases");

  useEffect(() => { setCasesHref(new URL("/#cases", ssoLoginUrl("/")).toString()); }, []);
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (hash !== "community") return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, [pathname, search]);

  function scrollTo(event: MouseEvent<HTMLAnchorElement>, id: string) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    if (window.location.hash !== `#${id}`) window.history.pushState(window.history.state, "", `#${id}`);
  }

  return <footer className="site-footer">
    <div className="site-footer-inner">
      <div className="site-footer-brand"><Link href="/" aria-label="临场首页"><img src={withBasePath("/icon.png")} width={34} height={34} alt="" /><span><strong>临场</strong><small>NARRATIVEOS</small></span></Link></div>
      <div className="site-footer-links">
        <nav aria-label="页脚导航">
          <a href={casesHref}>优质案例</a>
          <Link href="/#community" scroll={false} onClick={event => scrollTo(event, "community")}>Q&amp;A</Link>
          <button type="button" onClick={openAnnouncements}>公告</button>
        </nav>
        <div className="site-footer-legal"><a href="https://beian.miit.gov.cn" target="_blank" rel="noopener noreferrer"><span aria-hidden="true" />津ICP备2025028636号-2</a><small>© 2026 NarrativeOS</small></div>
      </div>
    </div>
  </footer>;
}
