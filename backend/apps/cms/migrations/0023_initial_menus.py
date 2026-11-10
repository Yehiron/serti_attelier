"""Copy the exact existing navigation. Historical models only; never republish pages."""
from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError

NOTE = 'Menús iniciales de Fase 6'
MAIN = [
    ('catalog', 'Joyería', 'Jewelry'),
    ('stones', 'Piedras', 'Stones'),
    ('collections', 'Colecciones', 'Collections'),
    ('personalize', 'Personaliza tus joyas', 'Customize your jewelry'),
    ('story', 'Nuestra historia', 'Our story'),
    ('contact', 'Contacto', 'Contact'),
]


def seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    Document = apps.get_model('cms', 'ContentDocument')
    Publication = apps.get_model('cms', 'MenuPublication')
    Page = apps.get_model('cms', 'Page')
    Revision = apps.get_model('cms', 'PageRevision')
    main = [{'link': {'kind': kind, 'label': {'es': es, 'en': en}}, 'visible': True} for kind, es, en in MAIN]
    footer = []
    for kind in ('terms', 'privacy', 'returns', 'shipping', 'cookies'):
        page = Page.objects.using(alias).filter(kind=kind, status='published').first()
        if not page or not page.version:
            continue
        revision = Revision.objects.using(alias).filter(page_id=page.pk).order_by('-published_at', '-pk').first()
        if revision:
            footer.append({'link': {'kind': 'page', 'target': page.pk, 'label': {lang: revision.snapshot[lang]['title'] for lang in ('es', 'en')}}, 'visible': True})
    for menu, items in (('main', main), ('footer', footer)):
        doc, created = Document.objects.using(alias).get_or_create(key='menu:' + menu)
        if not created:
            continue
        publication = Publication.objects.using(alias).create(menu=menu, snapshot=items, note=NOTE, published_by_repr='Equipo SERTI')
        doc.menu_items = items
        doc.menu_publication_id = publication.pk
        doc.published_version = 0
        doc.save(using=alias, update_fields=['menu_items', 'menu_publication', 'published_version'])


def reverse_seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    Document = apps.get_model('cms', 'ContentDocument')
    Publication = apps.get_model('cms', 'MenuPublication')
    Draft = apps.get_model('cms', 'DraftRevision')
    for menu in ('main', 'footer'):
        publications = Publication.objects.using(alias).filter(menu=menu)
        initial = publications.filter(note=NOTE).first()
        doc = Document.objects.using(alias).filter(key='menu:' + menu).first()
        if not initial:
            continue
        if publications.exclude(pk=initial.pk).exists() or (doc and (doc.draft_version or doc.menu_items != initial.snapshot or Draft.objects.using(alias).filter(document_id=doc.pk).exists())):
            raise IrreversibleError('Los menús ya fueron editados. Exporta y adapta su historial antes de revertir Fase 6.')
    for menu in ('main', 'footer'):
        initial = Publication.objects.using(alias).filter(menu=menu, note=NOTE).first()
        if initial:
            Document.objects.using(alias).filter(key='menu:' + menu, menu_publication_id=initial.pk).delete()
            Publication.objects.using(alias).filter(pk=initial.pk).delete()


class Migration(migrations.Migration):
    dependencies = [('cms', '0022_menupublication_redirect_and_more')]
    operations = [migrations.RunPython(seed, reverse_seed)]
