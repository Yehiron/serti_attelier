import test from 'node:test';
import assert from 'node:assert/strict';
import { parseWishlist, toggleWish, readWishlist, writeWishlist, type Wish } from './wishlist.ts';
const wish: Wish = { sku:'A1', slugs:{es:'anillo',en:'ring'},name:'Anillo',price:{amount_cents:15000,currency:'COP'},image:null,addedAt:1 };
test('wishlist toggles without duplicates and preserves localized slugs', () => {
 assert.deepEqual(toggleWish([],wish),[wish]); assert.deepEqual(toggleWish([wish],wish),[]);
 assert.deepEqual(parseWishlist(JSON.stringify([wish,wish])),[wish]);
});
test('wishlist tolerates corrupt, invalid or disabled storage', () => {
 for (const value of [null,'bad','{}','[null]',JSON.stringify([{...wish,price:{}}]),JSON.stringify([{...wish,image:{src:1}}])]) assert.deepEqual(parseWishlist(value),[]);
 const storage = {getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}};
 assert.deepEqual(readWishlist(storage),[]);assert.equal(writeWishlist(storage,[wish]),false);
});

test('wishlist refresh merges live data and preserves missing pieces for removal', async () => {
 const { mergeWishlist } = await import('./wishlist.ts');
 const live = { state: 'available' as const, slugs: { es: 'nuevo', en: 'new' }, name: 'Nuevo', image: null, price: { amount_cents: 20000, currency: 'COP' as const } };
 assert.deepEqual(mergeWishlist([wish], { A1: live }), [{ ...wish, slugs: live.slugs, name: live.name, image: live.image, price: live.price }]);
 assert.deepEqual(mergeWishlist([wish], { A1: { state: 'missing' } }), [wish]);
});
