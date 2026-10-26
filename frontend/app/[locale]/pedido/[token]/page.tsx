import { OrderPayment } from '@/components/order-payment';
import { orderViewState } from '@/lib/order-state';
import Link from 'next/link';
import { locale } from 'next/root-params';
import { notFound } from 'next/navigation';
import { getDictionary } from '../../dictionaries';
import { isLocale } from '@/lib/i18n';
import { ApiError, getOrder, getSettings } from '@/lib/api/server';
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
  const order = await getOrder(current, token).catch(error => { if (error instanceof ApiError && error.status === 404) notFound(); throw error; });
  const [dict, settings] = await Promise.all([getDictionary(), getSettings(current)]); const t = dict.commerce;
  const view = orderViewState(order); const heading = t[view.heading]; const active = view.active;
  const whatsapp = whatsappUrl(settings.whatsapp.number, `${t.whatsappOrder} ${order.number}`);
  return <main id="main" className="commerce-page order-page">
    <PageAlternates alternates={{ es: href('order','es',token), en: href('order','en',token) }} />
    <header className="page-heading">
      <p className="eyebrow">{t.order} · {order.number}</p>
      <h1 id="order-heading" tabIndex={-1} aria-live="polite">{heading}</h1>
    </header>
    <div className="order-layout">
      <section className="order-status">
        <OrderPayment order={order} token={token} locale={current} t={t} />
        {view.status === 'approved' && <p>{t.confirmationEmail}</p>}
        {(view.status === 'approved' || view.failed) && whatsapp && <a className="text-link" href={whatsapp} target="_blank" rel="noopener noreferrer">{t.contact} · WhatsApp ↗</a>}
        {view.status === 'awaiting_manual_payment' && <>
          <p className="whitespace-pre-line">{order.manual_instructions}</p>
          {whatsapp && <a className="text-link" href={whatsapp} target="_blank" rel="noopener noreferrer">WhatsApp · {order.number} ↗</a>}
        </>}
        {active && order.reservation_expires_at && <p>{t.deadline} <time dateTime={order.reservation_expires_at}>{formatDeadline(order.reservation_expires_at,current)} · Colombia</time></p>}
        <OrderLive status={view.retry ? 'pending' : view.status} deadline={order.reservation_expires_at} label={t.remaining} expired={t.expired} />
        {view.status === 'expired' && <Link className="button" href={href('catalog',current)}>{t.explore} ↗</Link>}
        <p>{order.wants_certificate ? t.certificateYes : t.certificateNo}</p>
        <p>{t.delivery} · {order.shipping.municipality}, {order.shipping.department}</p>
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
