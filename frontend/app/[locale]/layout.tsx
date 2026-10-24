import type { Metadata } from "next";
import { Cormorant_Garamond, Inter } from "next/font/google";
import { notFound } from "next/navigation";
import { locale } from "next/root-params";

import { isLocale, locales } from "@/lib/i18n";

import { getDictionary } from "./dictionaries";
import "../globals.css";

const serif = Cormorant_Garamond({
  variable: "--font-cormorant",
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  style: ["normal", "italic"],
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
  return {
    title: dict.meta.title,
    description: dict.meta.description,
    icons: { icon: "/favicon.svg" },
    alternates: { languages: { es: "/es", en: "/en" } },
  };
}

export default async function RootLayout({ children }: LayoutProps<"/[locale]">) {
  const current = await locale();
  if (!isLocale(current)) notFound();
  const dict = await getDictionary();

  return (
    <html lang={current} className={`${serif.variable} ${sans.variable}`}>
      <body>
        <a className="skip-link" href="#main">
          {dict.nav.skip}
        </a>
        {children}
      </body>
    </html>
  );
}
