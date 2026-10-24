import type { MetadataRoute } from 'next';
export default function robots(): MetadataRoute.Robots { return { rules: { userAgent: '*', allow: '/', disallow: ['/preview', '/api'] }, sitemap: `${process.env.PUBLIC_SITE_URL ?? 'https://serti.localhost'}/sitemap.xml` }; }
