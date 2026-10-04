export const TERMINAL_RENDER_STATUSES = new Set(["completed","failed","cancelled","blocked"]);
export const NON_TERMINAL_RENDER_EVENTS = new Set(["render_started","render_progress","render_stage"]);

export function isTerminalRenderStatus(status: unknown): boolean {
  return typeof status === "string" && TERMINAL_RENDER_STATUSES.has(status);
}

export function isNonTerminalRenderEvent(eventType: string): boolean {
  return NON_TERMINAL_RENDER_EVENTS.has(eventType);
}

export function shouldIgnoreRenderMutation(existingStatus: unknown,eventType: string): boolean {
  return isNonTerminalRenderEvent(eventType) && isTerminalRenderStatus(existingStatus);
}
