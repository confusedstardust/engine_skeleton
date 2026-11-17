"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import CommunityBoard from "../../../components/community-board";
import { AnnouncementPanel } from "../../../components/announcements";

export default function SupportPanel() {
  const announcements = useSearchParams().get("panel") === "announcements";
  useEffect(() => {
    if (window.parent === window || !document.referrer) return;
    const parentOrigin = new URL(document.referrer).origin;
    function close(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.defaultPrevented && !document.querySelector('[role="dialog"]')) {
        window.parent.postMessage("narrativeos:close-support", parentOrigin);
      }
    }
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  return <main className="community-support-embed">{announcements ? <AnnouncementPanel /> : <CommunityBoard />}</main>;
}
