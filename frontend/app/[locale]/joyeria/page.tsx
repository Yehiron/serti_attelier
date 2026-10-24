import { Listing, listingMetadata } from '@/components/listing';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata() {  return listingMetadata('catalog'); }
export default async function Page(props: PageProps<"/[locale]/joyeria">) {  return <Listing kind="catalog" searchParams={props.searchParams} />; }
