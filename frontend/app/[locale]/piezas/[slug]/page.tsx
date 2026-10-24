import { PieceDetail, pieceMetadata } from '@/components/piece-detail';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata(props: PageProps<'/[locale]/piezas/[slug]'>) { return pieceMetadata((await props.params).slug); }
export default async function Page(props: PageProps<'/[locale]/piezas/[slug]'>) { return <PieceDetail slug={(await props.params).slug} />; }
