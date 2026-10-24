import { EditorialPage, editorialMetadata } from '@/components/editorial-page';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata() { return editorialMetadata('personalize'); }
export default async function Page() { return <EditorialPage kind="personalize" />; }
