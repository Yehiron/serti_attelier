import type { MetadataRoute } from 'next';
export default function robots(): MetadataRoute.Robots { return { rules: { userAgent: '*', allow: '/', disallow: ['/preview', '/api', '/es/carrito', '/en/cart', '/es/checkout', '/en/checkout', '/es/pedido', '/en/order', '/es/buscar?', '/en/search?'] }, sitemap: `${process.env.PUBLIC_SITE_URL ?? 'https://serti.localhost'}/sitemap.xml` }; }
