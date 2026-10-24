from django.db import migrations


def seed(apps, schema_editor):
    db = schema_editor.connection.alias
    Page = apps.get_model('cms', 'Page')
    Service = apps.get_model('cms', 'PersonalizationService')
    Section = apps.get_model('cms', 'HomeSection')
    Collection = apps.get_model('catalog', 'Collection')
    pages = [
        ('terms', 'Términos y condiciones', 'Terms and conditions', 'terminos', 'terms'),
        ('privacy', 'Privacidad', 'Privacy', 'privacidad', 'privacy'),
        ('returns', 'Devoluciones', 'Returns', 'devoluciones', 'returns'),
        ('shipping', 'Envíos', 'Shipping', 'envios', 'shipping'),
        ('cookies', 'Cookies', 'Cookies', 'cookies', 'cookies'),
        ('manufacturer', 'Historia', 'Story', 'historia', 'story'),
        ('personalize', 'Personaliza', 'Customize', 'personaliza', 'customize'),
        ('contact', 'Contacto', 'Contact', 'contacto', 'contact'),
    ]
    for index, (kind, es, en, slug_es, slug_en) in enumerate(pages):
        body_es = ('Texto provisional — pendiente de revisión legal\n\n## Información\n\n## Contacto'
                   if index < 5 else 'Texto provisional — pendiente de revisión editorial')
        body_en = ('Provisional text — pending legal review\n\n## Information\n\n## Contact'
                   if index < 5 else 'Provisional text — pending editorial review')
        Page.objects.using(db).create(kind=kind, title=es, title_es=es, title_en=en,
            slug=slug_es, slug_es=slug_es, slug_en=slug_en,
            body=body_es, body_es=body_es, body_en=body_en, status='draft')
    services = [
        ('Grabado', 'Engraving', 'Un detalle íntimo que permanece.', 'An intimate detail that endures.'),
        ('Diseño a medida', 'Bespoke design', 'Una joya que nace de tu historia.', 'A jewel born from your story.'),
        ('Pieza inspirada en una vendida', 'Inspired by a sold piece', 'Una nueva interpretación, única para ti.', 'A new interpretation, uniquely yours.'),
        ('Compromiso y matrimonio', 'Engagement and wedding', 'Símbolos para una historia compartida.', 'Symbols for a shared story.'),
        ('Rediseño de joyas heredadas', 'Heirloom redesign', 'Una nueva vida para lo que atesoras.', 'A new life for what you treasure.'),
    ]
    for position, (es, en, desc_es, desc_en) in enumerate(services):
        Service.objects.using(db).create(title=es, title_es=es, title_en=en,
            description=desc_es, description_es=desc_es, description_en=desc_en,
            whatsapp_message='Hola SERTI, me interesa {service}. {url}',
            whatsapp_message_es='Hola SERTI, me interesa {service}. {url}',
            whatsapp_message_en='Hello SERTI, I am interested in {service}. {url}',
            is_active=False, position=position)
    sections = [
        ('hero', 'Un poco de tierra. / Un poco de eternidad.', 'A little earth. / A little eternity.', 'catalog', 'Explorar joyería', 'Explore jewelry'),
        ('statement', 'No es solo joyería. Es joyería atemporal.', "It's not just jewelry. It's timeless jewelry.", 'none', '', ''),
        ('stone_panels', 'Piedras que cuentan historias', 'Stones that tell stories', 'none', '', ''),
        ('collection_rail', 'Novedades y Destacados', 'New and featured', 'none', '', ''),
        ('story', 'Nuestra historia', 'Our story', 'story', 'Conocer SERTI', 'Discover SERTI'),
        ('personalize', 'Una pieza que solo puede ser tuya.', 'A piece that can only be yours.', 'personalize', 'Personalizar', 'Customize'),
    ]
    collection = Collection.objects.using(db).filter(name_es='Novedades y Destacados').first()
    for position, (kind, es, en, cta, label_es, label_en) in enumerate(sections):
        if kind == 'collection_rail' and collection is None:
            continue
        Section.objects.using(db).create(kind=kind, position=position,
            title=es, title_es=es, title_en=en, cta_kind=cta,
            cta_label=label_es, cta_label_es=label_es, cta_label_en=label_en,
            collection_id=collection.pk if kind == 'collection_rail' else None)


class Migration(migrations.Migration):
    dependencies = [('cms', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
