"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { clearStoredInviteCode, getStoredInviteCode, setStoredInviteCode } from "../invite-identity";

export default function LoginPage() {
  const router = useRouter();
  const [inviteCode, setInviteCode] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setInviteCode(getStoredInviteCode());
  }, []);

  function submitInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = inviteCode.trim();
    if (!code) return;
    setStoredInviteCode(code);
    setSaved(true);
    router.push("/history");
  }

  function clearInvite() {
    clearStoredInviteCode();
    setInviteCode("");
    setSaved(false);
  }

  return (
    <>
      <header className="top-nav">
        <Link className="brand brand-link" href="/">
          <div className="brand-seal">文</div>
          <div className="brand-copy">
            <span className="brand-name">临场 · 邀请码</span>
            <span className="brand-subtitle">INVITE ACCESS</span>
          </div>
        </Link>
        <nav className="nav-links" aria-label="邀请码导航">
          <Link href="/">新建任务</Link>
          <Link href="/history">生成记录</Link>
        </nav>
      </header>

      <main className="main-wrapper auth-wrapper">
        <section className="auth-panel" aria-labelledby="login-title">
          <div className="auth-copy">
            <span>内测身份</span>
            <h1 id="login-title">输入邀请码继续</h1>
            <p>每个邀请码对应一个独立身份，生成记录和游戏库只显示这个邀请码下的内容。</p>
          </div>

          <form className="auth-form" onSubmit={submitInvite}>
            <label>
              邀请码
              <input
                autoComplete="off"
                onChange={(event) => {
                  setInviteCode(event.target.value);
                  setSaved(false);
                }}
                placeholder="输入你的内测邀请码"
                value={inviteCode}
              />
            </label>
            <button className="btn primary" disabled={!inviteCode.trim()} type="submit">保存邀请码</button>
            <button className="btn outline" type="button" onClick={clearInvite}>清除本机邀请码</button>
            {saved ? <p className="form-note">邀请码已保存在当前浏览器。</p> : null}
          </form>
        </section>
      </main>
    </>
  );
}
