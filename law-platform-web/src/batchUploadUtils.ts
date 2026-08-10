// 批量导入的纯工具函数与常量，独立于组件以便复用与单元测试。

export const FAILURE_DELAY_OPTIONS = [
  { value: 5 * 1000, label: '5秒' },
  { value: 30 * 1000, label: '30秒' },
  { value: 60 * 1000, label: '1分钟' },
  { value: 2 * 60 * 1000, label: '2分钟' },
  { value: 5 * 60 * 1000, label: '5分钟' },
] as const;

export const DEFAULT_FAILURE_DELAY_MS = 2 * 60 * 1000;
// 保留旧导出，避免已有调用方突然失效；新组件使用可配置状态。
export const FAILURE_DELAY_MS = DEFAULT_FAILURE_DELAY_MS;
export const FAILURE_DELAY_STORAGE_KEY = 'knowledge-upload-failure-delay-ms';

export function normalizeFailureDelay(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return FAILURE_DELAY_OPTIONS.some((option) => option.value === parsed)
    ? parsed
    : DEFAULT_FAILURE_DELAY_MS;
}

export function loadFailureDelay(): number {
  try {
    return normalizeFailureDelay(window.localStorage.getItem(FAILURE_DELAY_STORAGE_KEY));
  } catch {
    return DEFAULT_FAILURE_DELAY_MS;
  }
}

export function saveFailureDelay(value: number): number {
  const normalized = normalizeFailureDelay(value);
  try {
    window.localStorage.setItem(FAILURE_DELAY_STORAGE_KEY, String(normalized));
  } catch {
    // 浏览器禁用存储时仍允许本次页面内使用。
  }
  return normalized;
}

export function failureDelayLabel(milliseconds: number): string {
  return FAILURE_DELAY_OPTIONS.find((option) => option.value === milliseconds)?.label
    ?? FAILURE_DELAY_OPTIONS.find((option) => option.value === DEFAULT_FAILURE_DELAY_MS)!.label;
}

export function durationLabel(milliseconds: number): string {
  if (milliseconds < 1000) return `${Math.round(milliseconds)} 毫秒`;
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0) parts.push(`${minutes}分钟`);
  if (seconds > 0) parts.push(`${seconds}秒`);
  return parts.length > 0 ? parts.join('') : '0秒';
}

// 倒计时统一显示 “分:秒”（如 5:00、0:05），便于失败等待提示。
export function countdownLabel(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}
