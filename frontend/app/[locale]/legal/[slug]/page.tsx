import { EditorialPage, editorialMetadata } from '@/components/editorial-page';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata(props: PageProps<"/[locale]/legal/[slug]">) { return editorialMetadata('legal', (await props.params).slug); }
export default async function Page(props: PageProps<"/[locale]/legal/[slug]">) { return <EditorialPage kind="legal" slug={(await props.params).slug} />; }
