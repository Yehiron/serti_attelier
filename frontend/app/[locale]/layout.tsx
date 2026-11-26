import { RouteScrollReset } from "@/components/route-scroll-reset";
import { ScrollReveal } from "@/components/scroll-reveal";
import { draftMode } from "next/headers";
import { Suspense } from "react";
import { Header, Footer, PreviewBar } from "@/components/site-shell";
import { siteUrl, getBrand } from "@/lib/api/server";
import { brandStyle, brandMetadata, originalBrand } from "@/lib/cms-brand";
import type { Metadata } from "next";
import { Cormorant_Garamond, Inter } from "next/font/google";
import { notFound } from "next/navigation";
import { locale } from "next/root-params";

import { isLocale, locales } from "@/lib/i18n";

import { getDictionary } from "./dictionaries";
import "../globals.css";

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;

// Fallback for Ninna only (docs/marca.md): not preloaded, so it is fetched only if used.
const serif = Cormorant_Garamond({
  variable: "--font-cormorant",
  subsets: ["latin"],
  weight: ["400"],
  style: ["normal", "italic"],
  preload: false,
});

const sans = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["300", "400", "500"],
});

export function generateStaticParams() {
  return locales.map((value) => ({ locale: value }));
}

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  const current = await locale(); if (!isLocale(current)) notFound();
  const brand = await getBrand(current).catch(() => originalBrand);
  return brandMetadata(brand, {
    ...((await draftMode()).isEnabled ? { robots: { index: false, follow: false }, referrer: "no-referrer" as const } : {}),
    metadataBase: new URL(siteUrl),
    title: { default: dict.meta.title, template: "%s | SERTI" },
    description: dict.meta.description,
    icons: {
      icon: [
        { url: "/favicon.svg", type: "image/svg+xml" },
        { url: "/icon-32.png", sizes: "32x32", type: "image/png" },
        { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      ],
      shortcut: "/favicon.ico",
      apple: "/apple-touch-icon.png",
    },
    alternates: { languages: { es: "/es", en: "/en" } },
  });
}

export default async function RootLayout({ children }: LayoutProps<"/[locale]">) {
  const current = await locale();
  if (!isLocale(current)) notFound();
  const dict = await getDictionary();
  return <Suspense fallback={<html data-scroll-behavior="smooth" lang={current} className={`${serif.variable} ${sans.variable}`}><body><main id="main" className="loading-shell">{dict.ui.loading}</main></body></html>}><SiteDocument current={current} dict={dict}>{children}</SiteDocument></Suspense>;
}

// Settings are request-time data: suspend the document until its typography is known.
async function SiteDocument({ current, dict, children }: { current: "es" | "en"; dict: Awaited<ReturnType<typeof getDictionary>>; children: React.ReactNode }) {
  const brand = await getBrand(current).catch(() => originalBrand);

  return (
    <html data-scroll-behavior="smooth" lang={current} className={`${serif.variable} ${sans.variable}`} style={brandStyle(brand)}>
      <body>
        <Suspense fallback={null}><RouteScrollReset /></Suspense>
        <ScrollReveal />
        <a className="skip-link" href="#main">
          {dict.nav.skip}
        </a>
        <Suspense fallback={<div className="header-placeholder" />}><Header locale={current} dict={dict} /></Suspense>
        <Suspense fallback={null}><PreviewBar dict={dict} /></Suspense>
        <Suspense fallback={<main id="main" className="loading-shell">{dict.ui.loading}</main>}>{children}</Suspense>
        <Suspense fallback={null}><Footer locale={current} dict={dict} /></Suspense>
      </body>
    </html>
  );
}
