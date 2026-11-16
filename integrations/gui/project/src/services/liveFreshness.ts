/** Compare timestamps from the same server clock, then age them monotonically. */
export function captureIsFresh(capturedAt: string | null | undefined, serverTime: string | undefined,
  receivedAt: number, now: number, requestDuration = 0, maxAge = 10000): boolean {
  if (!capturedAt || !serverTime) return false;
  const serverAge = Date.parse(serverTime) - Date.parse(capturedAt);
  const elapsed = now - receivedAt;
  return Number.isFinite(serverAge) && Number.isFinite(elapsed) && Number.isFinite(requestDuration)
    && serverAge >= 0 && elapsed >= 0 && requestDuration >= 0
    && serverAge + elapsed + requestDuration < maxAge;
}
