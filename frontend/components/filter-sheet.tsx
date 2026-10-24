'use client';
import { useRef, type ReactNode } from 'react';
export function FilterSheet({ children, label, close }: { children: ReactNode; label: string; close: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  return <><button className="button mobile-filter-trigger" onClick={() => dialog.current?.showModal()}>{label} +</button><dialog ref={dialog} className="filter-dialog" aria-label={label}><button className="sheet-close" onClick={() => dialog.current?.close()}>{close} ×</button>{children}</dialog></>;
}
