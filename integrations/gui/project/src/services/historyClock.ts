import type { ServerClock } from '@/types/contracts';
import { localDateTimeValue } from '@/utils';

export function deviceTime(clock: ServerClock, monotonicNow = performance.now()): number {
  return clock.timestamp + Math.max(0, monotonicNow - clock.receivedAt);
}

export function deviceHistoryRange(clock: ServerClock, hours: number, monotonicNow = performance.now()) {
  const end = deviceTime(clock, monotonicNow);
  return {
    start: localDateTimeValue(new Date(end - hours * 3600000), true),
    end: localDateTimeValue(new Date(end), true),
  };
}
