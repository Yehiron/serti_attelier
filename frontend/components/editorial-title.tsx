import { titleLines } from '@/lib/title';

/** Multi-line editorial title; with several lines the last one is italic, as in the brand prototype. */
export function EditorialTitle({ text }: { text: string }) {
  const lines = titleLines(text);
  return lines.map((line, index) => (
    <span key={index} className="title-line">
      {lines.length > 1 && index === lines.length - 1 ? <em>{line}</em> : line}
    </span>
  ));
}
