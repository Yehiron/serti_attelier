import { Listing, listingMetadata } from '@/components/listing';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata() {  return listingMetadata('search'); }
export default async function Page(props: PageProps<"/[locale]/buscar">) {  return <Listing kind="search" searchParams={props.searchParams} />; }
