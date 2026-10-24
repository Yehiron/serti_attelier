import assert from "node:assert/strict";
import { test } from "node:test";

import { localeFromAcceptLanguage, localeFromPath, negotiateLocale } from "./i18n.ts";

test("reads the locale from the first path segment", () => {
  assert.equal(localeFromPath("/en/piezas/anillo"), "en");
  assert.equal(localeFromPath("/es"), "es");
  assert.equal(localeFromPath("/fr/x"), null);
  assert.equal(localeFromPath("/"), null);
});

test("picks the highest-weighted supported language", () => {
  assert.equal(localeFromAcceptLanguage("fr-FR,en;q=0.8,es;q=0.9"), "es");
  assert.equal(localeFromAcceptLanguage("en-US,en;q=0.9"), "en");
  assert.equal(localeFromAcceptLanguage("de,fr;q=0.5"), null);
  assert.equal(localeFromAcceptLanguage("en;q=0"), null);
  assert.equal(localeFromAcceptLanguage(null), null);
});

test("cookie beats the browser language, Spanish is the fallback", () => {
  assert.equal(negotiateLocale("en", "es-CO"), "en");
  assert.equal(negotiateLocale(undefined, "en-GB"), "en");
  assert.equal(negotiateLocale("xx", "de"), "es");
});
