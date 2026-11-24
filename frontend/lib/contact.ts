export const topics = ['piece', 'custom', 'appointment', 'order', 'other'] as const;
export type Topic = typeof topics[number];
export type ContactInput = { name: string; email: string; phone: string; topic: string; piece_sku: string; message: string; preferred_channel: string; accepted_privacy_version: number | null; locale: string; website: string; elapsed_ms: number };
export function contactPrefill(search: string) {
  const params = new URLSearchParams(search);
  const sku = (params.get('pieza') || params.get('piece') || '').slice(0, 64);
  return { sku, topic: sku ? 'piece' : params.get('tema') === 'personalizacion' ? 'custom' : '' };
}
export function validateContact(data: ContactInput): string[] {
  const errors: string[] = [];
  if (!data.name.trim() || data.name.trim().length > 120) errors.push('name');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email) || data.email.length > 254) errors.push('email');
  if (data.phone && (!/^\+?[0-9 ()-]+$/.test(data.phone) || data.phone.replace(/\D/g, '').length < 8 || data.phone.replace(/\D/g, '').length > 15)) errors.push('phone');
  if (!topics.includes(data.topic as Topic)) errors.push('topic');
  if (data.message.trim().length < 20 || data.message.trim().length > 2000) errors.push('message');
  if (!['email', 'whatsapp'].includes(data.preferred_channel)) errors.push('preferred_channel');
  if (!data.accepted_privacy_version) errors.push('accepted_privacy_version');
  return errors;
}
export function contactWhatsApp(data: Pick<ContactInput, 'name' | 'message' | 'piece_sku'>, topic: string, locale: string) {
  return `${locale === 'es' ? 'Hola, soy' : 'Hello, I am'} ${data.name}. ${locale === 'es' ? 'Quiero hablar sobre' : 'I would like to talk about'} ${topic || (locale === 'es' ? 'una consulta' : 'an inquiry')}${data.piece_sku ? ` ${locale === 'es' ? 'sobre la pieza' : 'about piece'} ${data.piece_sku}` : ''}: ${data.message}`.slice(0, 600);
}
