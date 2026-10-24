import { Listing, listingMetadata } from '@/components/listing';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata(props: PageProps<"/[locale]/joyeria/[category]">) { const { category } = await props.params; return listingMetadata('category', category); }
export default async function Page(props: PageProps<"/[locale]/joyeria/[category]">) { const { category } = await props.params; return <Listing kind="category" slug={category} searchParams={props.searchParams} />; }
