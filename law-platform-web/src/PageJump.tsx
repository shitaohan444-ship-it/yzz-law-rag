import { FormEvent, useState } from 'react';

interface PageJumpProps {
  pageCount: number;
  disabled?: boolean;
  onJump: (page: number) => void;
}

export function clampPage(value: number, pageCount: number): number {
  const max = Math.max(1, Math.floor(pageCount));
  if (!Number.isFinite(value)) return 1;
  return Math.min(max, Math.max(1, Math.floor(value)));
}

export default function PageJump({ pageCount, disabled = false, onJump }: PageJumpProps) {
  const [value, setValue] = useState('');

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const target = Number(value);
    if (value.trim() === '' || !Number.isFinite(target)) return;
    onJump(clampPage(target, pageCount));
    setValue('');
  }

  return (
    <form className="page-jump" aria-label="跳转到指定页" onSubmit={submit}>
      <input
        aria-label="跳转页码"
        type="number"
        inputMode="numeric"
        placeholder="页码"
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
      />
      <button type="submit" disabled={disabled || value.trim() === ''}>
        跳转
      </button>
    </form>
  );
}
