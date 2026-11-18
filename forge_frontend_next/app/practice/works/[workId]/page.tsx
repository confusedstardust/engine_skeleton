"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { forgeApi } from "../../../../lib/api-client";
import { workApi } from "../../../../lib/work-api";
import { withBasePath } from "../../../base-path";
import styles from "./public-work.module.css";

type PlayerWork = {
  id: string;
  title: string;
  summary?: string;
  kind: string;
  subject?: string | null;
  grade?: string | null;
  tags?: string[];
  version: number;
  published_at?: string;
  gesture_ar?: boolean;
};

type PlayerData = { work: PlayerWork; src: string; isPrivate: boolean };

/**
 * One visual player for public Teacher Plaza links and the owner's saved cover.
 * Public mode uses the published immutable version; the owner view uses the
 * latest private version only after the existing authenticated owner check.
 * A revoked/unpublished work is NEVER made public by the fallback.
 */
export default function PublicWorkPage() {
  const { workId } = useParams<{ workId: string }>();
  const [player, setPlayer] = useState<PlayerData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!/^[0-9a-f]{32}$/.test(workId || "")) {
      setError("作品链接无效");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    setPlayer(null);
    let active = true;

    async function loadPrivate() {
      const { work } = await workApi.get(workId);
      const version = work.versions.find(item => item.id === work.current_version_id);
      if (!version) throw new Error("Saved work has no current version");
      if (!active) return;
      setPlayer({
        isPrivate: true,
        // Use the authenticated private asset URL directly so its server-side
        // CSP and sandbox headers protect the user. Never blob-wrap untrusted HTML.
        src: withBasePath(`/api/forge/works/${workId}/assets/${version.id}/index.html`),
        work: {
          id: work.id, title: work.title, summary: work.summary, kind: work.kind,
          subject: work.subject, grade: work.grade, tags: work.tags,
          version: version.version_number,
        },
      });
    }

    async function load() {
      const ownerView = new URLSearchParams(window.location.search).get("owner") === "1";
      try {
        if (ownerView) {
          await loadPrivate();
        } else {
          try {
            const result = await forgeApi<PlayerWork>(`/public/works/${workId}`);
            if (active) {
              setPlayer({
                work: result,
                src: withBasePath(`/api/forge/public/works/${result.id}/index.html`),
                isPrivate: false,
              });
            }
          } catch {
            // Public 404 or revocation: only the authenticated owner can fall
            // back to a private version via /works/{id} and /works/.../assets.
            await loadPrivate();
          }
        }
      } catch {
        if (active) setError("作品未发布、已撤回，或暂时无法访问");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [workId]);

  // Separate origin is mandatory: never grant a main-site/srcDoc frame camera access.
  const gestureAr = Boolean(player && !player.isPrivate && player.work.gesture_ar);
  const arOrigin = typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)
    ? "http://localhost:8040" : "https://ar.narrativeos.cn";
  const frameSrc = gestureAr ? `${arOrigin}/works/${workId}/index.html` : player?.src;

  return <main className={styles.page}>
    {player?.isPrivate && <Link className={styles.back} href="/history">我的作品</Link>}
    {loading && <p className={styles.message}>正在读取互动学习作品…</p>}
    {error && !loading && <p role="alert" className={styles.message}>{error}</p>}
    {player && !loading && <section className={styles.content}>
      <div className={styles.title}>
        <h1>{player.work.title}</h1>
        <p>{[player.work.subject, player.work.grade, `V${player.work.version}`].filter(Boolean).join(" · ")}</p>
        {player.work.summary && <p>{player.work.summary}</p>}
      </div>
      <div className={styles.viewer}>
        <iframe key={frameSrc} title={player.work.title}
          sandbox={gestureAr ? "allow-scripts allow-same-origin" : "allow-scripts"}
          allow={gestureAr ? "camera; fullscreen" : "fullscreen"}
          allowFullScreen referrerPolicy="no-referrer"
          src={frameSrc} />
      </div>
    </section>}
  </main>;
}
