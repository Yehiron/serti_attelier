import { normalizePhone } from './commerce.ts';

type Step = 'data' | 'delivery' | 'summary';
type Messages = { required: string; emailInvalid: string; phoneInvalid: string };
export function validateCheckoutFields(data: FormData, steps: Step[], messages: Messages) {
  const fields: Record<string, string[]> = {};
  const names = [...(steps.includes('data') ? ['contact.name', 'contact.email', 'contact.phone'] : []), ...(steps.includes('delivery') ? ['shipping.municipality_code', 'shipping.address_line'] : []), ...(steps.includes('summary') ? ['terms', 'privacy'] : [])];
  for (const name of names) if (!String(data.get(name) ?? '').trim()) fields[name] = [messages.required];
  if (steps.includes('data')) {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(data.get('contact.email') ?? '').trim())) fields['contact.email'] = [messages.emailInvalid];
    if (!/^\+\d{10,15}$/.test(normalizePhone(String(data.get('contact.phone') ?? '')))) fields['contact.phone'] = [messages.phoneInvalid];
  }
  return fields;
}
