import type { Problem } from './types.ts';
export class ApiError extends Error {
  status: number;
  problem: Problem;
  constructor(status: number, problem: Problem) { super(problem.detail || problem.title || problem.code); this.name = 'ApiError'; this.status = status; this.problem = problem; }
}
export async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, { code: 'request_failed', ...body });
  }
  return response.json() as Promise<T>;
}
