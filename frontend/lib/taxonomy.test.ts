import test from 'node:test';
import assert from 'node:assert/strict';
import { taxonomyAlternates } from './taxonomy.ts';
import type { Taxonomy } from './api/types.ts';
const es: Taxonomy = { categories: [{slug:'anillos',name:'Anillos',cover_image:null,children:[]}],stones:[],collections:[],materials:[] };
const en: Taxonomy = { ...es, categories: [{...es.categories[0],slug:'rings',name:'Rings'}] };
test('taxonomy locale pairing uses locale-independent model ordering', () => {
 assert.deepEqual(taxonomyAlternates('category','es','anillos',es,en),{es:'/es/joyeria/anillos',en:'/en/jewelry/rings'});
 assert.deepEqual(taxonomyAlternates('category','en','rings',en,es),{en:'/en/jewelry/rings',es:'/es/joyeria/anillos'});
});
test('mismatched taxonomy snapshots fall back to the other home', () => {
 assert.equal(taxonomyAlternates('category','es','anillos',es,{...en,categories:[]}).en,'/en');
});
