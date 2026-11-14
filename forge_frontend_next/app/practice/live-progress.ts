import { withBasePath } from "../base-path";
import { forgeApi } from "../../lib/api-client";
import type { TimelineEvent } from "./creation-timeline";

export type LearningPlan = {
  learning_goal: string;
  interaction_method: string;
  key_concepts: string[];
};
export type BuildTask = {
  id: string;
  status: string;
  phase?: string;
  attempts?: number;
  output?: string;
  error?: string;
  artifact_id?: string;
  timeline?: TimelineEvent[];
  elapsed_ms?: number;
  learning_plan?: LearningPlan;
  public_brief?: string;
};

/**
 * One live EventSource, with an authenticated GET fallback when streams are
 * unavailable, idle, interrupted, or blocked by the reverse proxy.
 *
 * Every event carries a complete snapshot: reconnects replace the timeline
 * instead of duplicating stages. Closing a stream NEVER cancels a model run.
 */
export async function followBuildTask(
  endpoint: "html" | "animations",
  identifier: string,
  startedAt: number,
  onUpdate: (task: BuildTask) => void,
  isMounted: () => boolean,
): Promise<BuildTask> {
  const statusPath = `/nar-agent/${endpoint}/${identifier}`;
  return new Promise<BuildTask>((resolve, reject) => {
    let settled = false;
    let channel: EventSource | null = null;
    let polling = false;
    let lastEventAt = Date.now();
    let lastConnectAttempt = 0;
    let fallback = false;

    const cleanup = () => {
      channel?.close();
      channel = null;
      window.clearInterval(watchdog);
    };
    const finish = (task: BuildTask) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(task);
    };
    const fail = (error: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    };
    const accept = (task: BuildTask) => {
      if (settled || !task || task.id !== identifier || typeof task.status !== "string") return;
      lastEventAt = Date.now();
      if (!isMounted()) { fail(new Error("页面已关闭")); return; }
      onUpdate(task);
      if (task.status !== "RUNNING") finish(task);
    };
    const poll = async () => {
      if (settled || polling) return;
      polling = true;
      try {
        accept(await forgeApi<BuildTask>(statusPath));
      } catch {
        // Temporary connection errors must not mark the background model failed.
        if (!channel || channel.readyState === EventSource.CLOSED) {
          // Continue retrying: the final status remains the source of truth.
          fallback = true;
        }
      } finally { polling = false; }
    };
    const connect = () => {
      if (settled || typeof EventSource === "undefined") { fallback = true; return; }
      if (channel) channel.close();
      lastConnectAttempt = Date.now();
      try {
        channel = new EventSource(withBasePath(statusPath + "/events"), { withCredentials: true });
        channel.addEventListener("progress", event => {
          try { accept(JSON.parse((event as MessageEvent<string>).data) as BuildTask); }
          catch { void poll(); }
        });
        channel.addEventListener("complete", event => {
          try { accept(JSON.parse((event as MessageEvent<string>).data) as BuildTask); }
          catch { void poll(); }
        });
        channel.addEventListener("stream-error", () => {
          // The upstream connection failed; EventSource may reconnect while
          // polling continues to guarantee a final result.
          fallback = true;
          channel?.close(); channel = null;
          void poll();
        });
        channel.onerror = () => {
          fallback = true;
          // Leave EventSource in CONNECTING: browsers retry with cookies.
          void poll();
        };
        channel.onopen = () => { fallback = false; };
      } catch {
        channel = null;
        fallback = true;
      }
    };

    const watchdog = window.setInterval(() => {
      if (settled) return;
      if (!isMounted()) {
        fail(new Error("页面已关闭"));
        return;
      }
      if (Date.now() - startedAt > 930000) {
        fail(new Error("等待超时，请重新打开创作记录检查最终状态。"));
        return;
      }
      const quiet = Date.now() - lastEventAt;
      // Periodic fallback covers buffering proxies and lost final events;
      // a healthy SSE stream does not issue repeated browser-side GETs.
      if (fallback || !channel || quiet > 18000) void poll();
      if ((!channel || channel.readyState === EventSource.CLOSED) &&
          Date.now() - lastConnectAttempt > 12000) connect();
    }, 2000);

    connect();
    // Read the first status promptly even when the proxy blocks SSE.
    if (!channel) void poll();
  });
}
