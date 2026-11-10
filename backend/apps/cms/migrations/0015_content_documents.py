from django.db import migrations


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    Document = apps.get_model("cms", "ContentDocument")
    Home = apps.get_model("cms", "HomePublication")
    Page = apps.get_model("cms", "Page")
    Revision = apps.get_model("cms", "PageRevision")
    home = Home.objects.using(alias).order_by("-published_at", "-pk").first()
    Document.objects.using(alias).get_or_create(key="home", defaults={"home_publication_id": home.pk if home else None})
    for page in Page.objects.using(alias).all().iterator():
        revision = Revision.objects.using(alias).filter(page_id=page.pk).order_by("-version").first()
        Document.objects.using(alias).get_or_create(key=f"page:{page.kind}", defaults={"page_revision_id": revision.pk if revision else None})


def backwards(apps, schema_editor):
    # Documents may contain current version/pointer state or restoration history.
    # Keep them on data-only reversal; reversing 0014 removes the schema explicitly.
    pass


class Migration(migrations.Migration):
    dependencies = [("cms", "0014_alter_homesection_options_contentdocument_and_more")]
    operations = [migrations.RunPython(forwards, backwards)]
