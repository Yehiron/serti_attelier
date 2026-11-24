'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import type { Settings } from '@/lib/api/types';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import { whatsappUrl } from '@/lib/api/format';
import { contactPrefill, contactWhatsApp, topics, validateContact, type ContactInput } from '@/lib/contact';
import { WhatsAppIcon } from './whatsapp';

type Copy = Dictionary['contact'];
const socialNames: Record<string, string> = { instagram: 'Instagram', facebook: 'Facebook', tiktok: 'TikTok', pinterest: 'Pinterest' };
export function Contact({ settings, locale, copy: t }: { settings: Settings; locale: 'es' | 'en'; copy: Copy }) {
  const [data, setData] = useState<ContactInput>({ name: '', email: '', phone: '', topic: '', piece_sku: '', message: '', preferred_channel: 'email', accepted_privacy_version: null, locale, website: '', elapsed_ms: 0 });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false); const [sent, setSent] = useState(false);
  const start = useRef(0); const summary = useRef<HTMLDivElement>(null); const thanks = useRef<HTMLHeadingElement>(null);
  useEffect(() => { start.current = Date.now(); const timer = window.setTimeout(() => { const prefill = contactPrefill(window.location.search); setData(d => ({ ...d, topic: prefill.topic, piece_sku: prefill.sku })); }, 0); return () => window.clearTimeout(timer); }, []);
  useEffect(() => { if (Object.keys(errors).length) summary.current?.focus(); }, [errors]);
  useEffect(() => { if (sent) thanks.current?.focus(); }, [sent]);
  const privacy = settings.legal_pages.find(p => p.kind === 'privacy');
  const topicLabel = topics.includes(data.topic as typeof topics[number]) ? t[data.topic as typeof topics[number]] : '';
  const wa = whatsappUrl(settings.whatsapp.number, contactWhatsApp(data, topicLabel, locale));
  const update = (key: keyof ContactInput, value: string | number | null) => setData(d => ({ ...d, [key]: value }));
  const attrs = (name: string) => ({ 'aria-invalid': !!errors[name], 'aria-describedby': errors[name] ? `${name}-error` : undefined });
  const fieldMessage = (name: string) => t.fieldErrors[name as keyof typeof t.fieldErrors] || t.required;
  const shortError = (name: string) => locale === 'es' ? ({ name: 'Escribe tu nombre', email: 'Correo inválido', phone: 'Celular inválido', topic: 'Elige un motivo' }[name] || t.required) : ({ name: 'Enter your name', email: 'Invalid email', phone: 'Invalid mobile', topic: 'Choose a subject' }[name] || t.required);
  const error = (name: string) => errors[name] ? <span className="field-error" id={`${name}-error`}>{errors[name]}</span> : null;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validateContact(data); if (invalid.length) { setErrors(Object.fromEntries(invalid.map(k => [k, fieldMessage(k)]))); return; }
    setErrors({}); setBusy(true);
    try {
      const response = await fetch('/api/v1/contact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...data, elapsed_ms: Date.now() - start.current }) });
      if (!response.ok) { const result = await response.json().catch(() => ({})); const mapped: Record<string, string> = {}; if (result.errors) for (const [key, value] of Object.entries(result.errors)) mapped[key] = key in t.fieldErrors ? fieldMessage(key) : Array.isArray(value) ? value.join(' ') : String(value); if (result.code === 'consent_required') mapped.accepted_privacy_version = fieldMessage('accepted_privacy_version'); if (!Object.keys(mapped).length) mapped.form = response.status === 429 ? t.throttle : t.network; setErrors(mapped); return; }
      setSent(true);
    } catch { setErrors({ form: t.network }); } finally { setBusy(false); }
  }
  const waButton = settings.whatsapp.general_url && <a className="contact-outline" href={settings.whatsapp.general_url} target="_blank" rel="noopener noreferrer">{t.openWhatsApp} ↗</a>;
  const blank = (key: 'name' | 'email' | 'phone', placeholder: string, caption: string) => <span className={`contact-blank contact-${key}`}><input id={`contact-${key}`} aria-label={t[key]} type={key === 'email' ? 'email' : key === 'phone' ? 'tel' : 'text'} autoComplete={key === 'phone' ? 'tel' : key} placeholder={placeholder} value={data[key]} maxLength={key === 'name' ? 120 : key === 'phone' ? 30 : 254} onChange={e => update(key, e.target.value)} {...attrs(key)} /><small id={errors[key] ? `${key}-error` : undefined} className={errors[key] ? "contact-caption-error" : undefined}>{errors[key] ? shortError(key) : caption}</small></span>;
  return <section className="contact-layout">
    {sent ? <div className="contact-letter contact-thanks"><h2 ref={thanks} tabIndex={-1}>{t.successTitle}</h2><p>{t.successLead} {data.name}. {t.successReply} {data.preferred_channel === 'email' ? t.emailChannel : t.whatsapp}.</p><Link className="text-link" href={`/${locale}`}>{t.explore} ↗</Link>{waButton}</div> : <form className="contact-letter" onSubmit={submit} noValidate>
      <div className="contact-letter-head"><span>{t.to}</span><span>Colombia · {new Date().getFullYear()}</span></div>
      <p className="contact-salute">{t.salute}</p>
      {Object.keys(errors).length > 0 && <div className="contact-summary" role="alert" aria-live="assertive" tabIndex={-1} ref={summary}><strong>{t.errors}</strong><ul>{Object.entries(errors).map(([key, value]) => <li key={key}>{key === 'form' ? value : <a href={`#contact-${key}`}>{value}</a>}</li>)}</ul></div>}
      <p className="contact-prose">{t.nameLead} {blank('name', t.namePlaceholder, t.nameShort)} {t.topicLead} <span className="contact-blank contact-topic"><select id="contact-topic" aria-label={t.topic} value={data.topic} onChange={e => update('topic', e.target.value)} {...attrs('topic')}><option value="">{t.choose}</option>{topics.map(topic => <option key={topic} value={topic}>{t[topic]}</option>)}</select>{errors.topic && <small id="topic-error" className="contact-caption-error">{shortError('topic')}</small>}</span>{data.piece_sku && <> {t.about} {data.piece_sku}</>}. {t.emailLead} {blank('email', t.emailPlaceholder, t.email)} {t.phoneLead} {blank('phone', t.phonePlaceholder, t.optional)}.</p>
      <input type="hidden" name="piece_sku" value={data.piece_sku} />
      <textarea id="contact-message" aria-label={t.message} placeholder={t.messagePlaceholder} maxLength={2000} value={data.message} onChange={e => update('message', e.target.value)} {...attrs('message')} />{error('message')}<div className="contact-counter">{data.message.length} / 2000</div>
      <div className="contact-sign"><div><p className="contact-closing">{t.closing}</p><fieldset className="contact-prefer" id="contact-preferred_channel" {...attrs('preferred_channel')} aria-label={t.channel}>{(['email', 'whatsapp'] as const).map(channel => <label key={channel}><input type="radio" name="channel" checked={data.preferred_channel === channel} onChange={() => update('preferred_channel', channel)} />{channel === 'email' ? t.email : t.whatsapp}</label>)}{error('preferred_channel')}</fieldset>
      <label className="contact-consent" htmlFor="contact-accepted_privacy_version"><input id="contact-accepted_privacy_version" type="checkbox" checked={!!data.accepted_privacy_version} onChange={e => update('accepted_privacy_version', e.target.checked ? settings.legal_versions?.privacy ?? null : null)} {...attrs('accepted_privacy_version')} /><span>{privacy ? <Link href={privacy.href} target="_blank">{t.privacy} ↗</Link> : t.privacy}</span></label>{error('accepted_privacy_version')}</div>
      <div className="contact-trap" aria-hidden="true"><label>Website<input name="website" tabIndex={-1} autoComplete="off" value={data.website} onChange={e => update('website', e.target.value)} /></label></div><button className="contact-seal" disabled={busy} type="submit" aria-label={busy ? t.sending : t.send}><span>{busy ? t.sending : t.seal}</span></button></div>
    </form>}
    {settings.whatsapp.general_url && <><div className="contact-or">{t.or}</div><section className="contact-whatsapp"><div className="contact-wa-icon"><WhatsAppIcon /></div><div><h2>{t.talk}</h2><p>{t.waDescription}</p></div>{waButton}</section></>}
    {wa && (data.name.trim() || data.message.trim()) && <a className="text-link contact-continue" href={wa} target="_blank" rel="noopener noreferrer">{t.continue} ↗</a>}
    <div className="contact-details">{settings.support_email && <div><b>{t.email}</b><a href={`mailto:${settings.support_email}`}>{settings.support_email}</a></div>}<div><b>{t.atelier}</b>{t.visits}</div>{settings.social.length > 0 && <div><b>{t.social}</b>{settings.social.map(s => <a key={s.network} href={s.url} target="_blank" rel="noopener noreferrer">{socialNames[s.network] ?? s.network} ↗ </a>)}</div>}</div>
  </section>;
}
