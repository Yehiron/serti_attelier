import { manage } from './support';

export default function globalTeardown(): void {
  if (process.env.E2E_KEEP_DATA === '1') {
    console.log('E2E_KEEP_DATA=1: se conservan los datos E2E.');
    return;
  }
  console.log(manage('e2e_cleanup'));
}
