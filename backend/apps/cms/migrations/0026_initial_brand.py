"""Freeze existing values without publishing any unrelated draft."""
from copy import deepcopy
from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError

NOTE = 'Identidad inicial de Fase 7'
ORIGINAL = {'wine':'#651c32','crimson':'#8a1538','cream':'#ead9cb','paper':'#dfc9b8','ink':'#330414','olive':'#7a7256','olive-deep':'#58513d','title_font':'ninna','text_font':'inter','title_scale':100,'text_scale':100,'logo_light':None,'logo_dark':None,'monogram_light':None,'monogram_dark':None,'footer':None,'icon':None,'sharing':None}


def seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    Document = apps.get_model('cms','ContentDocument')
    Publication = apps.get_model('cms','BrandPublication')
    Settings = apps.get_model('core','SiteSettings')
    if Document.objects.using(alias).filter(key='brand:identity').exists():
        return
    value = deepcopy(ORIGINAL)
    config = Settings.objects.using(alias).first()
    if config:
        value.update(title_scale=config.title_scale, text_scale=config.text_scale)
    publication = Publication.objects.using(alias).create(snapshot=value, note=NOTE, published_by_repr='Equipo SERTI')
    Document.objects.using(alias).create(key='brand:identity', brand_identity=value, brand_publication_id=publication.pk, published_version=0)


def reverse_seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    Document = apps.get_model('cms','ContentDocument')
    Publication = apps.get_model('cms','BrandPublication')
    Draft = apps.get_model('cms','DraftRevision')
    doc = Document.objects.using(alias).filter(key='brand:identity').first()
    initial = Publication.objects.using(alias).filter(note=NOTE).first()
    if not initial:
        if doc:
            raise IrreversibleError('Exporta la identidad de marca antes de revertir: no es la semilla inicial.')
        return
    if (Publication.objects.using(alias).exclude(pk=initial.pk).exists() or not doc or doc.brand_publication_id != initial.pk or doc.draft_version or doc.brand_identity != initial.snapshot or Draft.objects.using(alias).filter(document_id=doc.pk).exists()):
        raise IrreversibleError('La identidad ya fue editada. Exporta su contenido e historial antes de revertir Fase 7.')
    # Legacy settings retain their columns; preserve the source values on rollback.
    Settings = apps.get_model('core','SiteSettings')
    Settings.objects.using(alias).all().update(title_scale=initial.snapshot['title_scale'], text_scale=initial.snapshot['text_scale'])
    Document.objects.using(alias).filter(pk=doc.pk).delete()
    Publication.objects.using(alias).filter(pk=initial.pk).delete()


class Migration(migrations.Migration):
    dependencies = [('cms','0025_brandpublication_and_more'), ('core','0008_sitesettings_text_scale_sitesettings_title_scale')]
    operations = [migrations.RunPython(seed, reverse_seed)]
