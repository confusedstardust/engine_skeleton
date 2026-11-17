"use client";
import { WorkspaceFooter } from "@narrativeos/ui/workspace-chrome";
import BrandLogo from "./brand-logo";
import { withBasePath } from "../app/base-path";
import { portalHref } from "@narrativeos/ui/app-links";
import { useBrowserOrigin } from "@narrativeos/ui/workspace-sidebar";
import { useAnnouncements, useQuestions } from "./announcements";

export default function SiteFooter() {
  const openAnnouncements = useAnnouncements();
  const openQuestions = useQuestions();
  const origin = useBrowserOrigin();
  const casesHref = portalHref("/teacher-ecosystem/", origin, process.env.NEXT_PUBLIC_SSO_ORIGIN);

  return <WorkspaceFooter brand="临场" logo={<BrandLogo size={34} />} homeHref={withBasePath("/")}
    navLabel="页脚导航" cases={{ href: casesHref, label: "优质案例" }}
    community={openQuestions}
    announcements={{ label: "公告", onClick: openAnnouncements }} />;
}
