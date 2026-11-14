(() => {
  const script = document.currentScript;
  if (window.top !== window) return;
  const endpoint = new URL("./visit", script.src);
  const basePath = endpoint.pathname.slice(0, -"/play/_telemetry/visit".length);
  const visitorKey = "narrativeos:forge-visitor";
  const beijingDay = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" });
  let reportedDay = "";

  function reportVisibleVisit() {
    if (document.visibilityState !== "visible") return;
    const path = location.pathname.slice(basePath.length);
    if (script.dataset.excludeAdmin && /^\/admin(?:\/|$)/.test(path)) return;
    const day = beijingDay.format(new Date());
    if (reportedDay === day) return;

    try {
      let visitorId = localStorage.getItem(visitorKey);
      if (!visitorId) {
        visitorId = crypto.randomUUID();
        localStorage.setItem(visitorKey, visitorId);
      }
      reportedDay = day;
      void fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ visitor_id: visitorId }),
        keepalive: true,
      }).then(response => {
        if (!response.ok && reportedDay === day) reportedDay = "";
      }).catch(() => {
        if (reportedDay === day) reportedDay = "";
      });
    } catch {
      // Browsers that block storage do not participate in this metric.
    }
  }

  reportVisibleVisit();
  document.addEventListener("visibilitychange", reportVisibleVisit);
  // Check again when a long-lived page crosses the Beijing date boundary.
  setInterval(reportVisibleVisit, 60_000);
})();
