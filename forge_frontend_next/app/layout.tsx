import { ToastProvider } from "../components/ui/toast";
import { Suspense } from "react";
import ForgeChrome from "../components/forge-chrome";
import { ConfirmationProvider } from "../components/ui/modal";
import Script from "next/script";
import { AnnouncementsProvider } from "../components/announcements";
import type { Metadata } from "next";
import "@xyflow/react/dist/style.css";
import "@narrativeos/ui/styles.css";
import "./globals.css";
import { withBasePath } from "./base-path";

export const metadata: Metadata = {
  title: "临场 · AI叙事课堂生成平台",
  description: "为课堂文本生成可玩的 WebGAL 叙事游戏、教师流程与学生任务。"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const solutionTitleFontUrl = withBasePath("/fonts/narrativeos-solution-title.ttf");
  return (
    <html lang="zh-CN">
      <head>
        <style>{`@font-face { font-family: "NarrativeOS Solution Serif"; src: url("${solutionTitleFontUrl}") format("truetype"); font-display: swap; }`}</style>
      </head>
      <body><Script src={withBasePath("/play/_telemetry/visitor.js")} data-exclude-admin="true" /><ToastProvider><ConfirmationProvider><Suspense><AnnouncementsProvider><ForgeChrome>{children}</ForgeChrome></AnnouncementsProvider></Suspense></ConfirmationProvider></ToastProvider></body>
    </html>
  );
}
