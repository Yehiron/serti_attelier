import { OrderPayment } from '@/components/order-payment';
import './tracking.css';
import { fulfillmentTimeline, orderViewState } from '@/lib/order-state';
import Link from 'next/link';
import { locale } from 'next/root-params';
import { notFound } from 'next/navigation';
import { getDictionary } from '../../dictionaries';
import { isLocale } from '@/lib/i18n';
import { ApiError, getOrder, getSettings, emptySettings } from '@/lib/api/server';
import { formatCOP, whatsappUrl } from '@/lib/api/format';
import { formatDeadline } from '@/lib/commerce';
import { href } from '@/lib/routes';
import { PageAlternates } from '@/lib/metadata';
import { Media } from '@/components/media';
import { Totals } from '@/components/commerce-totals';
import { OrderLive } from '@/components/order-live';
// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata() {
  const dict = await getDictionary();
  return { title: dict.commerce.order, robots: { index: false, follow: false } };
}
export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const current = await locale(); if (!isLocale(current)) notFound(); const { token } = await params;
  const [dict, settings] = await Promise.all([getDictionary(), getSettings(current).catch(() => emptySettings)]); const t = dict.commerce;
  const result = await getOrder(current, token).catch(error => { if (error instanceof ApiError && [404,410,429].includes(error.status)) return error.status; throw error; });
  if (result === 404 || result === 410) notFound();
  const contact = <>{settings.whatsapp.general_url && <a className="text-link" href={settings.whatsapp.general_url} target="_blank" rel="noopener noreferrer">WhatsApp ↗</a>}{settings.support_email && <a className="text-link" href={`mailto:${settings.support_email}`}>{t.contact} · {settings.support_email}</a>}</>;
  if (typeof result === 'number') return <main id="main" className="commerce-page order-page"><header className="page-heading"><p className="eyebrow">SERTI · {t.order}</p><h1>{result === 429 ? t.tooManyRequests : t.linkUnavailable}</h1></header><div className="order-contact">{contact}</div></main>;
  const order = result;
  const view = orderViewState(order); const terminal = ['cancelled', 'returned'].includes(order.fulfillment.status); const heading = order.payment_review && !terminal ? t.paymentReview : order.fulfillment.status !== 'unfulfilled' ? t[order.fulfillment.status] : t[view.heading]; const active = view.active && !terminal && !order.payment_review;
  const timeline = fulfillmentTimeline(order.fulfillment, view.status === 'approved');
  const whatsapp = whatsappUrl(settings.whatsapp.number, `${t.whatsappOrder} ${order.number}`);
  return <main id="main" className="commerce-page order-page">
    <PageAlternates alternates={{ es: href('order','es',token), en: href('order','en',token) }} />
    <header className="page-heading">
      <p className="eyebrow">{t.order} · {order.number}</p>
      <h1 id="order-heading" tabIndex={-1} aria-live="polite">{heading}</h1>
    </header>
    <div className="order-layout">
      <section className="order-status">
        {order.fulfillment.status === 'cancelled' && <p>{view.status === 'approved' ? t.approved : t.paymentVoided} · {t.cancelled}</p>}
        <OrderPayment order={order} token={token} locale={current} t={t} paused={terminal || order.payment_review} />
        {order.fulfillment.status === 'cancelled' && <p>{t.cancelledHelp}</p>}
        {order.fulfillment.status === 'returned' && <p>{t.returnedHelp}</p>}
        <section className="order-tracking" aria-label={t.progress}>
          <h2>{t.progress}</h2>
          <ol className="order-timeline">{timeline.map(step => <li key={step.key} aria-current={step.current ? 'step' : undefined} data-future={step.future}>
            <span>{t[step.label_key]}</span>
            {step.at && <time dateTime={step.at}>{formatDeadline(step.at, current)}</time>}
          </li>)}</ol>
        </section>
        <section className="order-shipment" aria-label={t.shipment}>
          <h2>{t.shipment}</h2>
          {order.fulfillment.carrier && <p>{t.carrier} · {order.fulfillment.carrier}</p>}
          {order.fulfillment.tracking_number && <p>{t.trackingNumber} · {order.fulfillment.tracking_number}</p>}
          {order.fulfillment.tracking_url && <a className="text-link" href={order.fulfillment.tracking_url} target="_blank" rel="noopener noreferrer">{t.trackShipment} ↗</a>}
        </section>
        <div className="order-contact">{contact}</div>
        {!terminal && !order.payment_review && view.status === 'approved' && <p>{t.confirmationEmail}</p>}
        {!terminal && !order.payment_review && view.status === 'awaiting_manual_payment' && <>
          <p className="whitespace-pre-line">{order.manual_instructions}</p>
          {whatsapp && <a className="text-link" href={whatsapp} target="_blank" rel="noopener noreferrer">WhatsApp · {order.number} ↗</a>}
        </>}
        {active && order.reservation_expires_at && <p>{t.deadline} <time dateTime={order.reservation_expires_at}>{formatDeadline(order.reservation_expires_at,current)} · Colombia</time></p>}
        <OrderLive status={active ? (view.retry ? 'pending' : view.status) : 'inactive'} deadline={order.reservation_expires_at} label={t.remaining} expired={t.expired} />
        {view.status === 'expired' && <Link className="button" href={href('catalog',current)}>{t.explore} ↗</Link>}
        <p>{order.wants_certificate ? t.certificateYes : t.certificateNo}</p>
        <p>{t.delivery} · {order.shipping.municipality}{order.shipping.municipality.toLocaleLowerCase() !== order.shipping.department.toLocaleLowerCase() && `, ${order.shipping.department}`}</p>
      </section>
      <section aria-label={t.summary}>
        {order.items.map(item => <article className="cart-line" key={item.sku}>
          {item.image && <Media image={item.image} sizes="100px" />}
          <div><h3>{item.name}</h3><p>{item.piece_number ?? item.sku}</p>
            <p>{formatCOP(item.unit_price_cents - item.discount_cents,current)}</p>
            {item.discount_cents > 0 && <p>{t.discount}: {formatCOP(item.discount_cents,current)}</p>}
          </div>
        </article>)}
        <Totals data={order} locale={current} dict={dict} />
      </section>
    </div>
  </main>;
}
