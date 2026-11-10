import { notFound } from 'next/navigation';
import { locale } from 'next/root-params';
import { getPage, ApiError } from '@/lib/api/server';
import { isLocale } from '@/lib/i18n';
import { EditorialPage, editorialMetadata, type EditorialKind } from '@/components/editorial-page';

export const instant = false;
type Props = { params: Promise<{ missing: string[] }> };
async function resolve(props: Props) {
  const current = await locale(); if (!isLocale(current)) notFound();
  const { missing } = await props.params;
  if (missing.length !== 1) notFound();
  const slug = missing[0];
  try {
    const page = await getPage(current, slug);
    if (page.alternates[current] !== `/${current}/${slug}`) notFound();
    const kind: EditorialKind = ['manufacturer', 'personalize', 'contact'].includes(page.kind) ? page.kind as EditorialKind : 'legal';
    return { kind, slug };
  } catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); throw error; }
}
export async function generateMetadata(props: Props) { const { kind, slug } = await resolve(props); return editorialMetadata(kind, slug); }
export default async function Page(props: Props) { return <EditorialPage {...await resolve(props)} />; }
