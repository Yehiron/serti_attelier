import Link from "next/link";
import { locale } from "next/root-params";

import { locales } from "@/lib/i18n";

import { getDictionary } from "./dictionaries";

export default async function Home() {
  const current = await locale();
  const dict = await getDictionary();

  return (
    <main id="main" className="flex min-h-svh flex-col justify-between bg-wine px-gutter py-10 text-cream">
      <nav aria-label={dict.nav.language} className="flex justify-end gap-4 text-xs tracking-[0.18em] uppercase">
        {locales.map((value) => (
          <Link
            key={value}
            href={`/${value}`}
            aria-current={value === current ? "true" : undefined}
            className="opacity-60 hover:opacity-100 aria-[current=true]:opacity-100"
          >
            {value}
          </Link>
        ))}
      </nav>

      <section className="max-w-3xl">
        <p className="text-xs tracking-[0.18em] uppercase">{dict.home.eyebrow}</p>
        <h1 className="mt-7 mb-8 font-serif text-[clamp(3.5rem,8vw,7.5rem)] leading-[0.96] tracking-[-0.045em]">
          {dict.home.title[0]}
          <br />
          <em className="font-light">{dict.home.title[1]}</em>
        </h1>
        <p className="text-sm leading-relaxed opacity-75">{dict.home.lede}</p>
      </section>

      <p className="text-xs tracking-[0.1em] opacity-60">{dict.home.status}</p>
    </main>
  );
}
