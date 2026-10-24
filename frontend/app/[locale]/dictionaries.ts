import { notFound } from "next/navigation";
import { locale } from "next/root-params";

import { isLocale } from "@/lib/i18n";

import type es from "./dictionaries/es.json";

export type Dictionary = typeof es;

const dictionaries: Record<"es" | "en", () => Promise<Dictionary>> = {
  es: () => import("./dictionaries/es.json").then((m) => m.default),
  en: () => import("./dictionaries/en.json").then((m) => m.default),
};

export async function getDictionary(): Promise<Dictionary> {
  const current = await locale();
  if (!isLocale(current)) notFound();
  return dictionaries[current]();
}
