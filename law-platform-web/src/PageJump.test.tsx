import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PageJump, { clampPage } from './PageJump';

afterEach(() => cleanup());

describe('clampPage', () => {
  it('keeps an in-range page unchanged', () => {
    expect(clampPage(3, 10)).toBe(3);
    expect(clampPage(1, 10)).toBe(1);
    expect(clampPage(10, 10)).toBe(10);
  });

  it('clamps below-range and above-range values into [1, pageCount]', () => {
    expect(clampPage(0, 10)).toBe(1);
    expect(clampPage(-5, 10)).toBe(1);
    expect(clampPage(11, 10)).toBe(10);
    expect(clampPage(999, 10)).toBe(10);
  });

  it('floors fractional pages and treats non-finite input as page 1', () => {
    expect(clampPage(2.9, 10)).toBe(2);
    expect(clampPage(Number.NaN, 10)).toBe(1);
    expect(clampPage(Number.POSITIVE_INFINITY, 10)).toBe(1);
  });

  it('treats a non-positive pageCount as a single page', () => {
    expect(clampPage(5, 0)).toBe(1);
    expect(clampPage(5, -3)).toBe(1);
  });
});

describe('PageJump', () => {
  it('jumps to the entered page via the button and clears the input', () => {
    const onJump = vi.fn();
    render(<PageJump pageCount={8} onJump={onJump} />);
    const input = screen.getByLabelText('跳转页码');
    fireEvent.change(input, { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: '跳转' }));
    expect(onJump).toHaveBeenCalledTimes(1);
    expect(onJump).toHaveBeenCalledWith(5);
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('jumps when the form is submitted with Enter', () => {
    const onJump = vi.fn();
    render(<PageJump pageCount={8} onJump={onJump} />);
    fireEvent.change(screen.getByLabelText('跳转页码'), { target: { value: '3' } });
    fireEvent.submit(screen.getByRole('form', { name: '跳转到指定页' }));
    expect(onJump).toHaveBeenCalledWith(3);
  });

  it('clamps an out-of-range page to pageCount', () => {
    const onJump = vi.fn();
    render(<PageJump pageCount={4} onJump={onJump} />);
    fireEvent.change(screen.getByLabelText('跳转页码'), { target: { value: '99' } });
    fireEvent.click(screen.getByRole('button', { name: '跳转' }));
    expect(onJump).toHaveBeenCalledWith(4);
  });

  it('keeps the button disabled while the input is empty', () => {
    render(<PageJump pageCount={8} onJump={() => undefined} />);
    const button = screen.getByRole('button', { name: '跳转' });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText('跳转页码'), { target: { value: '2' } });
    expect(button).toBeEnabled();
  });

  it('disables input and button when disabled', () => {
    render(<PageJump pageCount={8} disabled onJump={() => undefined} />);
    expect(screen.getByLabelText('跳转页码')).toBeDisabled();
    expect(screen.getByRole('button', { name: '跳转' })).toBeDisabled();
  });
});
