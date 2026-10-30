import assert from 'node:assert/strict';
import test from 'node:test';
import { heroImages, slideIsEager } from './hero-carousel.ts';

const desktop = { src: '/wide.webp', srcset: '', width: 1921, height: 900, alt: 'Wide' };
const mobile = { src: '/portrait.webp', srcset: '', width: 750, height: 1000, alt: 'Portrait' };
test('each breakpoint has its own ordered sequence, including one-sided slides', () => {
  const slides = [{ image: desktop, mobile_image: null }, { image: null, mobile_image: mobile }, { image: desktop, mobile_image: mobile }];
  assert.deepEqual(heroImages(slides, false), [desktop, desktop]);
  assert.deepEqual(heroImages(slides, true), [mobile, mobile]);
  assert.deepEqual(heroImages([], true), []);
});
test('preload the next slide, including wraparound, while distant slides stay lazy', () => {
  assert.equal(slideIsEager(1, 0, 4), true);
  assert.equal(slideIsEager(2, 0, 4), false);
  assert.equal(slideIsEager(0, 3, 4), true);
  assert.equal(slideIsEager(3, 3, 4), true);
});
