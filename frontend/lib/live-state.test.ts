import test from 'node:test';
import assert from 'node:assert/strict';
import { liveState } from './live-state.ts';

test('the live state replaces a stale cached state', () => {
  assert.equal(liveState('available', { 'SRT-1': 'reserved' }, 'SRT-1'), 'reserved');
  assert.equal(liveState('reserved', { 'SRT-1': 'sold' }, 'SRT-1'), 'sold');
});

test('unknown, hidden or failed lookups keep the server state', () => {
  assert.equal(liveState('available', { 'SRT-1': 'unavailable' }, 'SRT-1'), 'available');
  assert.equal(liveState('sold', {}, 'SRT-1'), 'sold');
  assert.equal(liveState('preorder', null, 'SRT-1'), 'preorder');
});
