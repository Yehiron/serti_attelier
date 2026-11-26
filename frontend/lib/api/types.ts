export type Image = { src: string; srcset: string; width: number; height: number; alt: string; focal?: { x: number; y: number } };
export type Money = { amount_cents: number; currency: 'COP' };
export type Named = { slug: string; name: string; color?: string };
export type Taxon = Named & { slugs?: { es: string; en: string }; updated_at?: string | null; cover_image: string | null; cover?: Image | null; description?: string; seo_title?: string; seo_description?: string };
export type Category = Taxon & { children: Taxon[] };
export type Taxonomy = { categories: Category[]; collections: Taxon[]; stones: Taxon[]; materials: Taxon[] };
export type SaleState = 'available' | 'reserved' | 'sold' | 'preorder';
export type LiveState = SaleState | 'unavailable';
export type WishStatus = { state: 'missing' } | { state: SaleState; slugs: { es: string; en: string }; name: string; image: Image | null; price: Money };
export type PieceCard = Named & { alternates: Alternates; sku: string; category: Named | null; stones: Named[]; price: Money; sale_price: Money | null; sale_state: SaleState; is_new: boolean; image: Image | null; hover_image?: Image | null };
/** Short silent clip shown in the piece gallery; only `ready` videos reach the API. */
export type PieceVideo = { src: string; type: string; width: number; height: number; duration_seconds: number; alt: string; poster: Image };
export type PieceDetail = PieceCard & {
  video?: PieceVideo | null;
  updated_at: string | null; published_at: string | null; piece_number: string; short_description: string; long_description: string; story: string; care: string;
  attributes: { ring_size?: string | number; length_mm?: number; metal?: string; metal_purity?: string; carats?: number; weight_g?: number; dimensions_mm?: string }; materials: Named[]; collections: Named[];
  gallery: Image[]; related: PieceCard[]; seo: { title: string; description: string; alternates: Alternates };
  whatsapp_url: string | null;
  cta: { kind: 'add_to_cart' } | { kind: 'whatsapp'; reason: 'preorder' | 'reserved' | 'sold'; url: string | null };
};
export type Alternates = { es: string; en: string };
export type Catalog = { count: number; next: string | null; previous: string | null; results: PieceCard[]; facets: { stones: { slug: string; count: number }[]; price: { min_cents: number | null; max_cents: number | null } } };
export type Cta = { label: string; href: string; external: boolean };
export type StonePanel = Named & { description: string; image: Image | null; href: string };
export type HeroSlide = { image: Image | null; mobile_image: Image | null };
export type { Section } from './sections.generated';
import type { Section } from './sections.generated';
export type CmsSeo = { title: string; description: string; image: Image | null; noindex: boolean };
export type CmsMenuItem = { label: string; href: string; external: boolean; dropdown: 'catalog' | 'stones' | 'collections' | null };
export type CmsMenu = { items: CmsMenuItem[]; preview: boolean };
export type Home = { seo?: CmsSeo; sections: Section[]; published_at: string | null; preview: boolean };
export type PageKind = 'terms' | 'privacy' | 'returns' | 'shipping' | 'cookies' | 'manufacturer' | 'personalize' | 'contact';
export type CmsPage = { body_visible?: boolean; seo?: CmsSeo; process?: { schema_version?: 1; title: string; steps: { title: string; description: string }[] }; faq?: { schema_version?: 1; title: string; items: { question: string; answer_html: string }[] }; kind: PageKind; slug: string; title: string; body_html: string; version: number; updated_at: string; alternates: Alternates };
export type Personalization = { services: { id: string | number; title: string; description: string; image: Image | null; whatsapp_url: string | null }[] };
export type Settings = { business_locality?: string; business_region?: string; business_country?: string; appointment_only?: boolean; service_area?: string; opening_hours?: string; seo_home_title?: string; seo_home_description?: string; title_scale: number; text_scale: number; legal_versions?: { terms: number | null; privacy: number | null }; certificate_price_cents?: number; manual_reservation_hours?: number; whatsapp: { number: string | null; general_url: string | null }; social: { network: 'instagram' | 'facebook' | 'tiktok' | 'pinterest'; url: string }[]; support_email: string | null; legal_pages: { kind: PageKind; title: string; href: string }[] };
export type Problem = { code: string; title?: string; detail?: string; status?: number; skus?: string[]; errors?: Record<string, string[] | Record<string, string[]>> };

export type WompiCheckout = { checkout_url: string; fields: Record<string, string> };
export type PaymentStatus = 'pending' | 'approved' | 'declined' | 'voided' | 'cancelled' | 'error' | 'expired' | 'awaiting_manual_payment';
export type OrderPayment = { status: PaymentStatus; last_attempt: { reference: string; status: 'PENDING' | 'APPROVED' | 'DECLINED' | 'VOIDED' | 'ERROR'; payment_method_type: string | null } | null; can_retry: boolean };
export type PaymentDetails = { wompi: WompiCheckout | null; payment: OrderPayment; payment_unavailable?: boolean };

export type MilestoneKey = 'received' | 'paid' | 'preparing' | 'shipped' | 'delivered' | 'cancelled' | 'returned';
export type Fulfillment = { status: 'unfulfilled' | 'preparing' | 'shipped' | 'delivered' | 'cancelled' | 'returned'; carrier: string; tracking_number: string; tracking_url?: string; shipped_at: string | null; delivered_at: string | null; timeline: { key: MilestoneKey; label_key: MilestoneKey; at: string | null }[] };

export type { BrandIdentity } from '../cms-brand';

export type ContactReceived = { received: true };
