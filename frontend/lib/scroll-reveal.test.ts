import assert from 'node:assert/strict';
import test, { type TestContext } from 'node:test';
import { installScrollReveal } from './scroll-reveal.ts';

function setup(t: TestContext, reduced = false, supported = true) {
  const classes = () => {
    const values = new Set<string>();
    return { add: (s: string) => values.add(s), remove: (s: string) => values.delete(s), contains: (s: string) => values.has(s) };
  };
  const parent = {};
  const element = (top: number, card = false) => ({
    classList: classes(), parentElement: parent,
    style: { values: new Map<string, string>(), setProperty(key: string, value: string) { this.values.set(key, value); } },
    getClientRects: () => [1], getBoundingClientRect: () => ({ top, bottom: top + 200 }), matches: () => card,
  });
  const elements = [element(0), element(900), element(1400, true), element(1400, true)];
  let intersect: IntersectionObserverCallback;
  let mutation: () => void;
  let change: () => void;
  const observed = new Set<Element>();
  let disconnected = false;
  class Observer {
    constructor(callback: IntersectionObserverCallback) { intersect = callback; }
    observe(el: Element) { observed.add(el); }
    unobserve(el: Element) { observed.delete(el); }
    disconnect() { observed.clear(); }
  }
  class Mutations {
    constructor(callback: () => void) { mutation = callback; }
    observe() {}
    disconnect() { disconnected = true; }
  }
  const originalIntersection = globalThis.IntersectionObserver;
  const originalMutation = globalThis.MutationObserver;
  Object.assign(globalThis, { IntersectionObserver: Observer, MutationObserver: Mutations });
  t.after(() => Object.assign(globalThis, { IntersectionObserver: originalIntersection, MutationObserver: originalMutation }));
  const media = { matches: reduced, addEventListener: (_: string, cb: () => void) => { change = cb; }, removeEventListener() {} };
  const doc = { documentElement: { classList: classes() }, body: {}, querySelectorAll: (selector: string) => selector === '.motion-pending' ? elements.filter(el => el.classList.contains('motion-pending')) : elements };
  // Frames run synchronously so mutation rescans stay deterministic.
  const win = { innerHeight: 800, matchMedia: () => media, requestAnimationFrame: (cb: () => void) => { cb(); return 0; }, cancelAnimationFrame() {}, ...(supported ? { IntersectionObserver: Observer } : {}) };
  const cleanup = installScrollReveal(doc as unknown as Document, win as unknown as Window);
  return { elements, observed, doc, media, cleanup, disconnected: () => disconnected, mutate: () => mutation(), change: () => change(), enter: (index: number, ratio: number) => intersect([{ target: elements[index], isIntersecting: true, intersectionRatio: ratio }] as unknown as IntersectionObserverEntry[], {} as IntersectionObserver) };
}

test('visible content is untouched; offscreen cards stagger and unobserve at 15%', t => {
  const f = setup(t);
  assert.equal(f.elements[0].classList.contains('motion-pending'), false);
  assert.equal(f.observed.size, 3);
  assert.equal(f.elements[2].style.values.get('--reveal-delay'), '0ms');
  assert.equal(f.elements[3].style.values.get('--reveal-delay'), '70ms');
  f.enter(2, .1);
  assert.equal(f.elements[2].classList.contains('motion-pending'), true);
  f.enter(2, .15);
  assert.equal(f.elements[2].classList.contains('motion-pending'), false);
  assert.equal(f.observed.size, 2);
  f.mutate();
  assert.equal(f.observed.size, 2);
  f.cleanup();
  assert.equal(f.observed.size, 0);
  assert.equal(f.disconnected(), true);
  assert.equal(f.doc.documentElement.classList.contains('motion-ready'), false);
});

test('reduced motion and unsupported observers leave all content visible', t => {
  const reduced = setup(t, true);
  assert.equal(reduced.observed.size, 0);
  assert.ok(reduced.elements.every(el => !el.classList.contains('motion-pending')));
  reduced.cleanup();
  const unsupported = setup(t, false, false);
  assert.equal(unsupported.observed.size, 0);
  unsupported.cleanup();
});

test('switching reduced motion on reveals pending content immediately', t => {
  const f = setup(t);
  f.media.matches = true;
  f.change();
  assert.equal(f.observed.size, 0);
  assert.ok(f.elements.every(el => !el.classList.contains('motion-pending')));
  f.cleanup();
});
