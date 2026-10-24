import { Listing, listingMetadata } from '@/components/listing';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata(props: PageProps<"/[locale]/colecciones/[collection]">) { const { collection } = await props.params; return listingMetadata('collection', collection); }
export default async function Page(props: PageProps<"/[locale]/colecciones/[collection]">) { const { collection } = await props.params; return <Listing kind="collection" slug={collection} searchParams={props.searchParams} />; }
