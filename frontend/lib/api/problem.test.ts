import test from 'node:test';
import assert from 'node:assert/strict';
import { readResponse, ApiError } from './problem.ts';
test('problem+json preserves backend error code and HTTP status', async () => {
 await assert.rejects(readResponse(new Response(JSON.stringify({code:'piece_not_found',detail:'missing'}), {status:404,headers:{'Content-Type':'application/problem+json'}})), error => error instanceof ApiError && error.status === 404 && error.problem.code === 'piece_not_found');
});
test('non-JSON errors remain typed and successes return JSON', async () => {
 await assert.rejects(readResponse(new Response('bad gateway',{status:502})), error => error instanceof ApiError && error.status === 502 && error.problem.code === 'request_failed');
 assert.deepEqual(await readResponse(Response.json({count:2})),{count:2});
});
