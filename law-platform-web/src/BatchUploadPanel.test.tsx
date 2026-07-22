import { describe, expect, it } from 'vitest';
import { durationLabel } from './BatchUploadPanel';

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
