import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "文境 · AI叙事课堂生成平台",
  description: "为课堂文本生成可玩的 WebGAL 叙事游戏、教师流程与学生任务。"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
