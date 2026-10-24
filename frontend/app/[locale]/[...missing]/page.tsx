import { notFound } from 'next/navigation';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export default function Page() { notFound(); }
