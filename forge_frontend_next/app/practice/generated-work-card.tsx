"use client";

import { withBasePath } from "../base-path";
import { Button } from "../../components/ui/button";
import { ArrowUpRight } from "lucide-react";
import styles from "./practice.module.css";

export type GeneratedWork = {
  artifactId: string;
  title: string;
  kind: "html" | "animation";
  version: number;
};

export default function GeneratedWorkCard({
  work, onOpen, savedWorkId,
}: {
  work: GeneratedWork;
  onOpen: (id: string) => void;
  savedWorkId?: string;
}) {
  // Durable cover for saved works, temporary NarAgent thumbnail for draft artifacts.
  const cover = withBasePath(savedWorkId
    ? `/api/forge/works/${savedWorkId}/cover.png`
    : `/api/forge/nar-agent/artifacts/${work.artifactId}/preview.png`);
  return <Button type="button" variant="unstyled" className={styles.generatedCard} onClick={() => onOpen(work.artifactId)}
    aria-label={`打开作品：${work.title}`}>
    <img alt="" src={cover} loading="lazy" />
    <span className={styles.generatedCardContent}>
      <strong>{work.title}</strong>
      <small>{work.kind === "html" ? "互动网页" : "教学动画"} · V{work.version}</small>
      <span>打开作品 <ArrowUpRight size={14} strokeWidth={1.7} aria-hidden="true" /></span>
    </span>
  </Button>;
}
