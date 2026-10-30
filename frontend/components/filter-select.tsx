'use client';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';

export type FilterOption = { value: string; label: string; child?: boolean };
// Only one filter list open at a time, like the main menu.
const OPEN_EVENT = 'serti:filter-select-open';

/** A filter row that unfolds its options in place (listbox pattern); the value travels in a hidden input. */
export function FilterSelect({ name, label, options, defaultValue }: { name: string; label: string; options: FilterOption[]; defaultValue: string }) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [value, setValue] = useState(defaultValue);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const selectedIndex = Math.max(0, options.findIndex(option => option.value === value));

  useEffect(() => {
    if (!open) return;
    list.current?.focus();
    window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: id }));
    const other = (event: Event) => { if ((event as CustomEvent<string>).detail !== id) setOpen(false); };
    // On click, not pointerdown: closing on press shifts the rows below and the click would land elsewhere.
    const outside = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    window.addEventListener(OPEN_EVENT, other);
    document.addEventListener('click', outside);
    return () => { window.removeEventListener(OPEN_EVENT, other); document.removeEventListener('click', outside); };
  }, [open, id]);
  useEffect(() => {
    if (open) document.getElementById(`${id}-option-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [open, active, id]);

  const show = () => { setActive(selectedIndex); setOpen(true); };
  const close = () => { setOpen(false); trigger.current?.focus(); };
  const choose = (index: number) => { setValue(options[index].value); close(); };
  const onTriggerKey = (event: KeyboardEvent) => {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) { event.preventDefault(); show(); }
  };
  const onListKey = (event: KeyboardEvent) => {
    const last = options.length - 1;
    const moves: Record<string, number> = { ArrowDown: Math.min(last, active + 1), ArrowUp: Math.max(0, active - 1), Home: 0, End: last };
    if (event.key in moves) { event.preventDefault(); setActive(moves[event.key]); }
    else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(active); }
    else if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'Tab') setOpen(false);
  };

  return <div ref={root} className={`filter-select${open ? ' is-open' : ''}`}>
    <span id={`${id}-label`} className="filter-row-name">{label}</span>
    <button ref={trigger} id={`${id}-button`} type="button" className="filter-select-trigger" aria-haspopup="listbox" aria-expanded={open} aria-controls={`${id}-list`} aria-labelledby={`${id}-label ${id}-button`} onClick={() => (open ? setOpen(false) : show())} onKeyDown={onTriggerKey}>{options[selectedIndex]?.label}</button>
    <ul ref={list} id={`${id}-list`} role="listbox" aria-labelledby={`${id}-label`} tabIndex={-1} hidden={!open} aria-activedescendant={open ? `${id}-option-${active}` : undefined} onKeyDown={onListKey}>
      {options.map((option, index) => <li key={option.value || 'all'} id={`${id}-option-${index}`} role="option" aria-selected={index === selectedIndex} className={[index === active && 'is-active', option.child && 'is-child'].filter(Boolean).join(' ') || undefined} onClick={() => choose(index)} onPointerMove={() => setActive(index)}>{option.label}</li>)}
    </ul>
    <input type="hidden" name={name} value={value} />
  </div>;
}
