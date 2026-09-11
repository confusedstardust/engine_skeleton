"use client";

import { useEffect } from "react";
import { withBasePath } from "../base-path";
import { getCurrentUser, ssoLoginUrl } from "../invite-identity";

export default function LoginPage() {
  useEffect(() => {
    let active = true;
    void getCurrentUser().then((user) => {
      if (!active) return;
      window.location.replace(user ? withBasePath("/") : ssoLoginUrl("/"));
    });
    return () => {
      active = false;
    };
  }, []);

  return <main aria-busy="true" />;
}
