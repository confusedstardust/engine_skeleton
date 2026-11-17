"use client";
import { LoadingState } from './ui/state';
import { InlineFeedback } from './ui/feedback';
import { Button } from './ui/button';


import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import CommunityBoard from "./community-board";
import * as Dialog from "./ui/dialog";
import { boardApi, type BoardData, type BoardNotice } from "../lib/community";

type SupportPanel = "announcements" | "questions";

const AnnouncementsContext = createContext<(panel: SupportPanel) => void>(() => {});
export function useAnnouncements() {
  const open = useContext(AnnouncementsContext);
  return useCallback(() => open("announcements"), [open]);
}
export function useQuestions() {
  const open = useContext(AnnouncementsContext);
  return useCallback(() => open("questions"), [open]);
}

export function AnnouncementsProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const [panel, setPanel] = useState<SupportPanel | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const open = useCallback((next: SupportPanel) => {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setPanel(next);
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (params.get("announcement") === "1") {
      open("announcements");
      url.searchParams.delete("announcement");
    } else if (pathname === "/" && url.hash === "#community") {
      open("questions");
      url.hash = "";
    } else return;
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  }, [pathname, params, open]);

  useEffect(() => {
    if (panel || pathname !== "/" || params.get("workspace") === "1") return;
    try { if (localStorage.getItem("community-notice-seen")) return; } catch { return; }
    let active = true;
    void boardApi<BoardData>("/community").then(data => {
      if (!active || !data.announcements.length) return;
      try {
        if (localStorage.getItem("community-notice-seen")) return;
        localStorage.setItem("community-notice-seen", "1");
      } catch { return; }
      open("announcements");
    }).catch(() => { /* A failed automatic check must not interrupt the page. */ });
    return () => { active = false; };
  }, [pathname, params, panel, open]);

  return <AnnouncementsContext.Provider value={open}>{children}
    <Dialog.Root open={panel !== null} onOpenChange={value => { if (!value) setPanel(null); }}>
      <Dialog.Surface overlayClassName="community-dialog-overlay" className={`community-notice-dialog${panel === "questions" ? " community-questions-dialog" : ""}`}
        aria-describedby={undefined} onCloseAutoFocus={event => {
          if (returnFocus.current?.isConnected) { event.preventDefault(); returnFocus.current.focus({ preventScroll: true }); }
        }}>
        <Dialog.Title className="sr-only">{panel === "questions" ? "提问与答疑" : "公告"}</Dialog.Title>
        <Dialog.CloseButton className="community-dialog-close" aria-label={panel === "questions" ? "关闭问答" : "关闭公告"} />
        {panel === "questions" ? <CommunityBoard /> : panel === "announcements" ? <AnnouncementPanel /> : null}
      </Dialog.Surface>
    </Dialog.Root>
  </AnnouncementsContext.Provider>;
}

export function AnnouncementPanel() {
  const [notices, setNotices] = useState<BoardNotice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    void boardApi<BoardData>("/community").then(data => { if (active) setNotices(data.announcements); })
      .catch(reason => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);

  return <div className="community-notices"><div className="community-column-heading"><h2 className="community-notice-label">WHAT’S NEW</h2></div>
        {notices.length ? notices.map(notice => <article className="community-sticky" key={notice.id}><span className="sticky-tape" aria-hidden="true" /><time>{notice.created_at.slice(0, 10).replaceAll("-", ".")}</time><h4>{notice.title}</h4><p>{notice.content}</p><span className="sticky-signature">NarrativeOS</span></article>) : <article className="community-sticky"><span className="sticky-tape" aria-hidden="true" /><span className="sticky-label">NOTE TO CREATORS</span><h4>{loading ? <LoadingState as="span" inline>正在查看新消息…</LoadingState> : "欢迎来到创作角落"}</h4><p>{error ? "公告暂时无法加载，请稍后重试。" : "新公告会贴在这里。创作中遇到问题，欢迎在问答区留言。"}</p><span className="sticky-signature">NarrativeOS</span></article>}
        {error && <InlineFeedback >{error} <Button variant="unstyled" className="community-text-button" onClick={() => setRevision(value => value + 1)}>重试</Button></InlineFeedback>}
      </div>;
}
