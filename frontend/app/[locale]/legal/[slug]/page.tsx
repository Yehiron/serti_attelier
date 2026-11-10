import { notFound } from 'next/navigation';
import { locale } from 'next/root-params';
import { isLocale } from '@/lib/i18n';
import { getPage, ApiError } from '@/lib/api/server';
import { EditorialPage, editorialMetadata } from '@/components/editorial-page';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
async function canonicalSlug(props: PageProps<"/[locale]/legal/[slug]">) {
  const current = await locale(); if (!isLocale(current)) notFound();
  const { slug } = await props.params;
  try { const page = await getPage(current, slug); if (page.alternates[current] !== `/${current}/legal/${slug}`) notFound(); }
  catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); throw error; }
  return slug;
}
export async function generateMetadata(props: PageProps<"/[locale]/legal/[slug]">) { return editorialMetadata('legal', await canonicalSlug(props)); }
export default async function Page(props: PageProps<"/[locale]/legal/[slug]">) { return <EditorialPage kind="legal" slug={await canonicalSlug(props)} />; }
