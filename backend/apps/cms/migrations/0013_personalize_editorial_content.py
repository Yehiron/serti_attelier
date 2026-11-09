"""Seed exact approved copy; provenance makes forward/reverse operations repeatable."""
from copy import deepcopy
from django.db import migrations
from django.utils import timezone
import html
import markdown
import nh3

COPY = {'es': {'personalizeTitle': 'Personaliza tus joyas', 'storyTitle': 'Nuestra historia', 'contactTitle': 'Contacto', 'process': 'De una idea a tu joya', 'steps': ['Conversamos sobre tu idea', 'Elegimos piedra y metal', 'Apruebas el boceto', 'Taller y entrega'], 'prepare': 'Antes de escribirnos', 'prepareBody': 'Ten a mano la ocasión, fecha, piedra y metal, talla o largo, presupuesto aproximado y fotos de referencia.', 'inspiration': 'Esta ya encontró su dueño; la tuya está por hacerse.', 'faq': 'Preguntas frecuentes', 'questions': ['¿Cuánto cuesta una pieza a medida?', '¿Cuánto tiempo toma?', '¿Puedo devolver una pieza personalizada?', '¿Puedo solicitar un certificado?'], 'answers': ['El precio depende de la piedra, el metal y el trabajo de taller. Conversaremos contigo antes de cotizar.', 'Confirmamos el tiempo de taller y entrega antes de comenzar. Cuéntanos si tienes una fecha especial.', 'Consulta la política de devoluciones publicada y confirma las condiciones de tu encargo con nuestro equipo.', 'Consulta con nuestro equipo la disponibilidad y las condiciones del certificado de autenticidad.']}, 'en': {'personalizeTitle': 'Customize your jewelry', 'storyTitle': 'Our story', 'contactTitle': 'Contact', 'process': 'From an idea to your jewel', 'steps': ['We discuss your idea', 'We choose stone and metal', 'You approve the sketch', 'Atelier and delivery'], 'prepare': 'Before you write to us', 'prepareBody': 'Have your occasion, date, preferred stone and metal, size or length, approximate budget and reference photos ready.', 'inspiration': 'This one has found its person; yours is still to be made.', 'faq': 'Frequently asked questions', 'questions': ['How much does a custom piece cost?', 'How long does it take?', 'Can I return a personalized piece?', 'Can I request a certificate?'], 'answers': ['Price depends on the stone, metal and work involved. We will discuss your idea before quoting.', 'We confirm production and delivery times before beginning. Tell us about any special date.', 'Read our published returns policy and confirm the conditions of your commission with our team.', 'Ask our team about availability and conditions for a certificate of authenticity.']}}
MARKER = "cms_phase_1_seed"


def rendered(source):
    return nh3.clean(markdown.markdown(html.escape(source, quote=False)),
                     tags={"p", "a", "em", "strong"}, attributes={"a": {"href", "title"}},
                     url_schemes={"https", "mailto"}, link_rel="noopener noreferrer")


def seed(apps, schema_editor):
    db = schema_editor.connection.alias
    Page = apps.get_model("cms", "Page")
    Step = apps.get_model("cms", "ProcessStep")
    Faq = apps.get_model("cms", "FaqItem")
    Revision = apps.get_model("cms", "PageRevision")
    page = Page.objects.using(db).filter(kind="personalize").first()
    if not page or Revision.objects.using(db).filter(page=page, snapshot__has_key=MARKER).exists():
        return
    # Existing editorial rows mean this installation has already been customized.
    if Step.objects.using(db).filter(page=page).exists() or Faq.objects.using(db).filter(page=page).exists():
        return
    previous = Revision.objects.using(db).filter(page=page).order_by("-version").first()
    original = {field: getattr(page, field) for field in (
        "version", "status", "process_title", "process_title_es", "process_title_en",
        "faq_title", "faq_title_es", "faq_title_en")}
    original["published_at"] = page.published_at.isoformat() if page.published_at else None
    steps, faqs = [], []
    returns = Page.objects.using(db).filter(kind="returns").first()
    for index in range(4):
        values = {f"title_{lang}": COPY[lang]["steps"][index] for lang in ("es", "en")}
        row = Step.objects.using(db).create(page=page, position=index, title=values['title_es'],
            description='', description_es='', description_en='', **values)
        steps.append(row)
        values = {}
        for lang in ("es", "en"):
            values[f"question_{lang}"] = COPY[lang]["questions"][index]
            answer = COPY[lang]["answers"][index]
            if index == 2:
                slug = getattr(returns, f"slug_{lang}", "") or (returns.slug_es if returns else '')
                slug = slug or ("devoluciones" if lang == "es" else "returns")
                label = getattr(returns, f"title_{lang}", "") if returns else ''
                label = label or ("Devoluciones" if lang == "es" else "Returns")
                answer += f"\n\n[{label}](/{lang}/legal/{slug})"
            values[f"answer_{lang}"] = answer
        row = Faq.objects.using(db).create(page=page, position=index,
            question=values['question_es'], answer=values['answer_es'], **values)
        faqs.append(row)
    snapshot = deepcopy(previous.snapshot) if previous else {}
    for lang in ("es", "en"):
        for field, key in (("process_title", "process"), ("faq_title", "faq")):
            setattr(page, f"{field}_{lang}", COPY[lang][key])
        if lang not in snapshot:
            data = {field: getattr(page, f"{field}_{lang}") or getattr(page, f"{field}_es")
                    for field in ("title", "slug", "body")}
            snapshot[lang] = data | {"body_html": rendered(data["body"]), "source": {
                field: getattr(page, f"{field}_{lang}") for field in ("title", "slug", "body")}}
        data = snapshot[lang]
        data.setdefault("source", {}).update({f: getattr(page, f"{f}_{lang}")
                                               for f in ("process_title", "faq_title")})
        data.update({f: getattr(page, f"{f}_{lang}") for f in ("process_title", "faq_title")})
        data['process'] = {'title': COPY[lang]['process'], 'steps': [
            {'title': getattr(row, f'title_{lang}'), 'description': '', 'position': row.position,
             'source': {'title': getattr(row, f'title_{lang}'), 'description': ''}} for row in steps]}
        data['faq'] = {'title': COPY[lang]['faq'], 'items': [
            {'question': getattr(row, f'question_{lang}'), 'answer': getattr(row, f'answer_{lang}'),
             'answer_html': rendered(getattr(row, f'answer_{lang}')), 'position': row.position,
             'source': {'question': getattr(row, f'question_{lang}'), 'answer': getattr(row, f'answer_{lang}')}}
            for row in faqs]}
    snapshot[MARKER] = {'original': original,
        'steps': list(Step.objects.using(db).filter(pk__in=[r.pk for r in steps]).values()),
        'faqs': list(Faq.objects.using(db).filter(pk__in=[r.pk for r in faqs]).values())}
    # Dates are not needed to identify exact created content.
    for rows in (snapshot[MARKER]['steps'], snapshot[MARKER]['faqs']):
        for row in rows:
            row.pop('created_at', None)
            row.pop('updated_at', None)
    version = max(page.version, previous.version if previous else 0) + 1
    Revision.objects.using(db).create(page=page, version=version, snapshot=snapshot,
                                     published_by_repr="Migración de contenido")
    page.version, page.status, page.published_at = version, "published", timezone.now()
    page.process_title, page.faq_title = page.process_title_es, page.faq_title_es
    page.save(using=db)


def unseed(apps, schema_editor):
    db = schema_editor.connection.alias
    Revision = apps.get_model('cms', 'PageRevision')
    Page = apps.get_model('cms', 'Page')
    for revision in Revision.objects.using(db).filter(snapshot__has_key=MARKER):
        metadata = revision.snapshot[MARKER]
        for key, name in (('steps', 'ProcessStep'), ('faqs', 'FaqItem')):
            model = apps.get_model('cms', name)
            for values in metadata[key]:
                # Never remove a row changed since the migration.
                model.objects.using(db).filter(**values).delete()
        page = Page.objects.using(db).get(pk=revision.page_id)
        if page.version == revision.version:
            for field, value in metadata['original'].items():
                setattr(page, field, value)
            page.save(using=db)
        revision.delete(using=db)


class Migration(migrations.Migration):
    dependencies = [("cms", "0012_page_faq_title_page_faq_title_en_page_faq_title_es_and_more")]
    operations = [migrations.RunPython(seed, unseed)]
