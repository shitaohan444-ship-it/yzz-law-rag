import { beforeEach, describe, expect, it } from 'vitest';
import {
  countdownLabel,
  DEFAULT_FAILURE_DELAY_MS,
  durationLabel,
  FAILURE_DELAY_MS,
  FAILURE_DELAY_OPTIONS,
  FAILURE_DELAY_STORAGE_KEY,
  failureDelayLabel,
  loadFailureDelay,
  normalizeFailureDelay,
  saveFailureDelay,
} from './batchUploadUtils';

beforeEach(() => {
  window.localStorage.clear();
});

describe('durationLabel', () => {
  it('formats sub-second durations as milliseconds', () => {
    expect(durationLabel(0)).toBe('0 毫秒');
    expect(durationLabel(500)).toBe('500 毫秒');
  });

  it('omits zero hours and minutes for a seconds-only duration', () => {
    expect(durationLabel(21 * 1000)).toBe('21秒');
  });

  it('omits zero hours for a minutes-and-seconds duration', () => {
    expect(durationLabel((5 * 60 + 21) * 1000)).toBe('5分钟21秒');
  });

  it('keeps hours, minutes and seconds when all are non-zero', () => {
    expect(durationLabel((3600 + 2 * 60 + 3) * 1000)).toBe('1小时2分钟3秒');
  });
});

describe('FAILURE_DELAY_MS', () => {
  it('is two minutes', () => {
    expect(FAILURE_DELAY_MS).toBe(2 * 60 * 1000);
    expect(DEFAULT_FAILURE_DELAY_MS).toBe(FAILURE_DELAY_MS);
  });

  it('provides the requested five selectable delays', () => {
    expect(FAILURE_DELAY_OPTIONS).toEqual([
      { value: 5_000, label: '5秒' },
      { value: 30_000, label: '30秒' },
      { value: 60_000, label: '1分钟' },
      { value: 120_000, label: '2分钟' },
      { value: 300_000, label: '5分钟' },
    ]);
  });

  it('persists a valid delay and rejects unsupported stored values', () => {
    expect(loadFailureDelay()).toBe(120_000);
    expect(saveFailureDelay(30_000)).toBe(30_000);
    expect(localStorage.getItem(FAILURE_DELAY_STORAGE_KEY)).toBe('30000');
    expect(loadFailureDelay()).toBe(30_000);
    expect(failureDelayLabel(30_000)).toBe('30秒');

    localStorage.setItem(FAILURE_DELAY_STORAGE_KEY, '12345');
    expect(loadFailureDelay()).toBe(120_000);
    expect(normalizeFailureDelay(Number.NaN)).toBe(120_000);
  });
});

describe('countdownLabel', () => {
  it('formats whole minutes remaining', () => {
    expect(countdownLabel(2 * 60 * 1000)).toBe('2:00');
  });

  it('formats minutes and zero-padded seconds', () => {
    expect(countdownLabel(79 * 1000)).toBe('1:19');
    expect(countdownLabel(61 * 1000)).toBe('1:01');
  });

  it('rounds up sub-second remainders to the next second', () => {
    expect(countdownLabel(1500)).toBe('0:02');
  });

  it('never goes below zero', () => {
    expect(countdownLabel(0)).toBe('0:00');
    expect(countdownLabel(-5000)).toBe('0:00');
  });
});
