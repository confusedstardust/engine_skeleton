/** Show PUBLIC NarAgent diagnostics, not provider exceptions or stack traces. */
export function formatPracticeFailure(
  turn: { errorCode?: string | null; runId?: string | null; status: string },
  task?: Record<string, unknown>,
): string {
  const knownError = typeof task?.error === "string" ? task.error.trim().slice(0, 240) : "";
  const code = typeof task?.error_code === "string" ? task.error_code
    : turn.errorCode || "GENERATION_FAILED";
  const phases = new Set(["DESIGNING", "PLANNING", "DRAFTING", "BUILDING", "CHECKING", "FINALIZING"]);
  const phase = typeof task?.phase === "string" && phases.has(task.phase) ? task.phase : undefined;
  const runId = typeof task?.id === "string" ? task.id : turn.runId || "";
  const statusLine = turn.status === "UNKNOWN"
    ? "任务结果尚未确认，请勿重新提交同一生成任务。"
    : knownError || "本次生成失败，可根据错误码查询执行服务日志。";
  const details = [phase ? "阶段：" + phase : null, "错误码：" + code,
    runId ? "任务编号：" + runId : null].filter(Boolean).join(" · ");
  return statusLine + (details ? "（" + details + "）" : "");
}
