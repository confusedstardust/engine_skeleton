"use client";

import { UserRound } from "lucide-react";
import BrandLogo from "../../components/brand-logo";
import styles from "./practice.module.css";

type MessageRole = "user" | "assistant";

/** Reuses the shared brand logo and the signed-in profile image. Decorative only. */
export default function PracticeMessageAvatar({
  role, userAvatarUrl, userInitial, burst = false,
}: {
  role: MessageRole;
  userAvatarUrl?: string | null;
  userInitial?: string;
  burst?: boolean;
}) {
  return <span className={`${styles.messageAvatar} ${role === "assistant" ? styles.agentAvatar : styles.userAvatar}`} aria-hidden="true">
    {role === "assistant" ? <BrandLogo size={36} rounded={false} /> : <>
      <span className={styles.userAvatarFallback}>{userInitial || <UserRound size={19} strokeWidth={1.8} />}</span>
      {userAvatarUrl && <img className={styles.userAvatarImage} src={userAvatarUrl}
        alt="" referrerPolicy="no-referrer" onError={event => { event.currentTarget.hidden = true; }} />}
    </>}
    {burst && <span className={styles.avatarBurst} aria-hidden="true">
      {Array.from({ length: 8 }, (_, i) => <i key={i} />)}
    </span>}
  </span>;
}
