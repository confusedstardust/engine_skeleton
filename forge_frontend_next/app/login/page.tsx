"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { withBasePath } from "../base-path";
import {
  AuthMode,
  clearStoredInviteCode,
  getAuthMode,
  getCurrentUser,
  getStoredInviteCode,
  setStoredInviteCode,
  ssoLoginUrl,
} from "../invite-identity";

export default function LoginPage() {
  const [mode, setMode] = useState<AuthMode | null>(null);
  const [loadError, setLoadError] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      const configuredMode = await getAuthMode();
      if (!active) return;
      if (!configuredMode) {
        setLoadError("暂时无法确认登录方式，请稍后重试。");
        return;
      }
      if (configuredMode === "sso") {
        const user = await getCurrentUser();
        if (!active) return;
        window.location.replace(user ? withBasePath("/") : ssoLoginUrl("/"));
        return;
      }
      if (configuredMode === "sso_or_invite" && await getCurrentUser()) {
        if (active) window.location.replace(withBasePath("/"));
        return;
      }
      if (!active) return;
      setMode(configuredMode);
      setInviteCode(getStoredInviteCode());
    })();
    return () => {
      active = false;
    };
  }, []);

  function submitInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = inviteCode.trim();
    if (!code) return;
    setStoredInviteCode(code);
    setSaved(true);
    window.location.assign(withBasePath("/history"));
  }

  function clearInvite() {
    clearStoredInviteCode();
    setInviteCode("");
    setSaved(false);
  }

  if (loadError) return <main className="main-wrapper auth-wrapper"><p className="form-note">{loadError}</p></main>;
  if (!mode) return <main aria-busy="true" />;

  return (
    <>
      <header className="top-nav">
        <Link className="brand brand-link" href="/">
          <div className="brand-seal" aria-hidden="true"><img src={withBasePath("/icon.png")} alt="" /></div>
          <div className="brand-copy"><span className="brand-name">临场 · 邀请码</span><span className="brand-subtitle">INVITE ACCESS</span></div>
        </Link>
        <nav className="nav-links" aria-label="邀请码导航"><Link href="/">新建任务</Link><Link href="/history">生成记录</Link></nav>
      </header>
      <main className="main-wrapper auth-wrapper">
        <section className="auth-panel" aria-labelledby="login-title">
          <div className="auth-copy">
            <span>内测身份</span><h1 id="login-title">输入邀请码继续</h1>
            <p>每个邀请码对应一个独立身份，生成记录和游戏库只显示这个邀请码下的内容。</p>
          </div>
          <form className="auth-form" onSubmit={submitInvite}>
            <label>邀请码<input autoComplete="off" onChange={(event) => { setInviteCode(event.target.value); setSaved(false); }} placeholder="输入你的内测邀请码" value={inviteCode} /></label>
            <button className="btn primary" disabled={!inviteCode.trim()} type="submit">保存邀请码</button>
            <button className="btn outline" type="button" onClick={clearInvite}>清除本机邀请码</button>
            {saved ? <p className="form-note">邀请码已保存在当前浏览器。</p> : null}
          </form>
          {mode === "sso_or_invite" ? <a className="btn outline" href={ssoLoginUrl("/")}>使用 NarrativeOS 账号登录</a> : null}
        </section>
      </main>
    </>
  );
}
