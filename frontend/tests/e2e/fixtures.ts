import { test as base, type BrowserContext } from '@playwright/test';
export { expect } from '@playwright/test';
export type { Page, Locator } from '@playwright/test';

/** External checkout is fulfilled by stubWompi; everything else stays on the local stack. */
export async function localOnly(context: BrowserContext, baseURL: string) {
  const origin = new URL(baseURL).origin;
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return url.origin === origin || url.href === 'https://checkout.wompi.co/widget.js' ? route.continue() : route.abort('blockedbyclient');
  });
}

export const test = base.extend({
  context: async ({ context, baseURL }, runFixture) => {
    await localOnly(context, baseURL!);
    await runFixture(context);
  },
});
