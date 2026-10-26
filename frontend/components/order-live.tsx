'use client';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
export function OrderLive({ status, deadline, label, expired }: { status: string; deadline: string | null; label: string; expired: string }) {
  const router = useRouter(); const [now, setNow] = useState<number | null>(null);
  const active = status === 'pending' || status === 'awaiting_manual_payment';
  useEffect(() => {
    if (!active) return;
    const started = Date.now(); let refresh: number;
    function poll() { refresh = window.setTimeout(() => { router.refresh(); poll(); }, status === 'pending' && Date.now() - started < 120000 ? 5000 : 15000); }
    poll();
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(refresh); clearInterval(tick); };
  }, [active, status, router]);
  if (!active || !deadline || now === null) return null;
  const seconds = Math.max(0, Math.floor((new Date(deadline).getTime() - now) / 1000));
  return <p className="reservation-clock" role="timer" aria-label={label}>{seconds === 0 ? expired : `${label} · ${String(Math.floor(seconds / 3600)).padStart(2,'0')}:${String(Math.floor(seconds % 3600 / 60)).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}`}</p>;
}
