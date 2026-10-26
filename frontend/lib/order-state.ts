import type { PaymentDetails } from './api/types.ts';
export function orderViewState(order: PaymentDetails) {
  const status = order.payment.status;
  const onlineActive = status === 'pending' || status === 'declined' || status === 'error';
  const unavailable = onlineActive && order.payment_unavailable === true;
  const retry = onlineActive && order.payment.can_retry && !unavailable;
  return {
    status,
    heading: status === 'approved' ? 'approved' : status === 'expired' ? 'expired' : status === 'awaiting_manual_payment' ? 'manualHeading' : status === 'pending' ? 'completePayment' : 'orderFailed',
    active: status === 'pending' || status === 'awaiting_manual_payment' || retry,
    pay: status === 'pending' && !!order.wompi && !unavailable && !retry,
    confirming: status === 'pending' && order.payment.last_attempt?.status === 'PENDING',
    retry, unavailable,
    failed: ['declined', 'voided', 'error'].includes(status),
  } as const;
}
