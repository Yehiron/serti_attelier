export type Image = { src: string; srcset: string; width: number; height: number; alt: string };
export type Money = { amount_cents: number; currency: 'COP' };
export type Named = { slug: string; name: string };
export type Taxon = Named & { cover_image: string | null; cover?: Image | null };
export type Category = Taxon & { children: Taxon[] };
export type Taxonomy = { categories: Category[]; collections: Taxon[]; stones: Taxon[]; materials: Taxon[] };
export type SaleState = 'available' | 'reserved' | 'sold' | 'preorder';
export type LiveState = SaleState | 'unavailable';
export type PieceCard = Named & { sku: string; category: Named | null; stones: Named[]; price: Money; sale_price: Money | null; sale_state: SaleState; is_new: boolean; image: Image | null; hover_image?: Image | null };
/** Short silent clip shown in the piece gallery; only `ready` videos reach the API. */
export type PieceVideo = { src: string; type: string; width: number; height: number; duration_seconds: number; alt: string; poster: Image };
export type PieceDetail = PieceCard & {
  video?: PieceVideo | null;
  piece_number: string; short_description: string; long_description: string; story: string; care: string;
  attributes: { ring_size?: string | number; length_mm?: number; metal?: string; metal_purity?: string; carats?: number; weight_g?: number; dimensions_mm?: string }; materials: Named[]; collections: Named[];
  gallery: Image[]; related: PieceCard[]; seo: { title: string; description: string; alternates: Alternates };
  cta: { kind: 'add_to_cart' } | { kind: 'whatsapp'; reason: 'preorder' | 'reserved' | 'sold'; url: string | null };
};
export type Alternates = { es: string; en: string };
export type Catalog = { count: number; next: string | null; previous: string | null; results: PieceCard[]; facets: { stones: { slug: string; count: number }[]; price: { min_cents: number | null; max_cents: number | null } } };
export type Cta = { label: string; href: string; external: boolean };
export type StonePanel = Named & { description: string; image: Image | null; href: string };
export type HeroSlide = { image: Image | null; mobile_image: Image | null };
export type Section = { id: string | number } & (
  { kind: 'hero'; slides?: HeroSlide[]; title: string; subtitle: string; image: Image | null; cta: Cta | null } |
  { kind: 'category_grid'; title: string; subtitle: string; categories: (Named & { href: string; count: number; image: Image | null })[] } |
  { kind: 'statement'; title: string; body: string } |
  { kind: 'stone_panels'; title: string; subtitle: string; stones: StonePanel[] } |
  { kind: 'collection_rail'; title: string; subtitle: string; collection: Named & { href: string }; pieces: PieceCard[] } |
  { kind: 'story' | 'personalize' | 'banner'; title: string; body: string; image: Image | null; cta: Cta | null }
);
export type Home = { sections: Section[]; published_at: string | null; preview: boolean };
export type PageKind = 'terms' | 'privacy' | 'returns' | 'shipping' | 'cookies' | 'manufacturer' | 'personalize' | 'contact';
export type CmsPage = { process?: { title: string; steps: { title: string; description: string }[] }; faq?: { title: string; items: { question: string; answer_html: string }[] }; kind: PageKind; slug: string; title: string; body_html: string; version: number; updated_at: string; alternates: Alternates };
export type Personalization = { services: { id: string | number; title: string; description: string; image: Image | null; whatsapp_url: string | null }[] };
export type Settings = { title_scale: number; text_scale: number; legal_versions?: { terms: number | null; privacy: number | null }; certificate_price_cents?: number; manual_reservation_hours?: number; whatsapp: { number: string | null; general_url: string | null }; social: { network: 'instagram' | 'facebook' | 'tiktok' | 'pinterest'; url: string }[]; support_email: string | null; legal_pages: { kind: PageKind; title: string; href: string }[] };
export type Problem = { code: string; title?: string; detail?: string; status?: number; skus?: string[]; errors?: Record<string, string[] | Record<string, string[]>> };

export type WompiCheckout = { checkout_url: string; fields: Record<string, string> };
export type PaymentStatus = 'pending' | 'approved' | 'declined' | 'voided' | 'error' | 'expired' | 'awaiting_manual_payment';
export type OrderPayment = { status: PaymentStatus; last_attempt: { reference: string; status: 'PENDING' | 'APPROVED' | 'DECLINED' | 'VOIDED' | 'ERROR'; payment_method_type: string | null } | null; can_retry: boolean };
export type PaymentDetails = { wompi: WompiCheckout | null; payment: OrderPayment; payment_unavailable?: boolean };

export type MilestoneKey = 'received' | 'paid' | 'preparing' | 'shipped' | 'delivered' | 'cancelled' | 'returned';
export type Fulfillment = { status: 'unfulfilled' | 'preparing' | 'shipped' | 'delivered' | 'cancelled' | 'returned'; carrier: string; tracking_number: string; tracking_url?: string; shipped_at: string | null; delivered_at: string | null; timeline: { key: MilestoneKey; label_key: MilestoneKey; at: string | null }[] };
