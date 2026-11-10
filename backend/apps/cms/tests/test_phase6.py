"""Phase 6 invariants; integration cases use the configured PostgreSQL database."""

import json
from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse

from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
from apps.cms import selectors, services, visual_documents
from apps.cms.documents import ContentConflict, edit_document, get_document
from apps.cms.menus import menu_groups, public_menu, publish_menu, restore_menu, validate_items
from apps.cms.models import DraftRevision, MenuPublication, Page, Redirect
from apps.cms.page_options import internal_path, normalize_slug, public_seo, validate_seo
from apps.cms.phase6_views import missing_pairs, pending_translations
from apps.cms.publishing import pending_changes
from apps.cms.redirects import flatten, save_redirect
from apps.core.tests.test_dashboard_client import staff


@pytest.mark.parametrize(
    "source,expected",
    [(" ENVÍOS rápidos! ", "envios-rapidos"), ("Diseño & café", "diseno-cafe"), ("A__B", "a-b")],
)
def test_normalize(source, expected):
    assert normalize_slug(source) == expected


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.test/es/x",
        "//evil.test",
        "/es/%2f%2fevil",
        "/es/../x",
        "/es/api/x",
        "/en/preview/x",
        "/api/x",
        "/es/x?next=https://evil.test",
        "/es/x#y",
        "/es/x\\y",
        "/es/x\n",
        "/es/%252e%252e/x",
    ],
)
def test_internal_only(path):
    with pytest.raises(ValidationError):
        internal_path(path)


def test_chains_and_cycles():
    rows = [
        SimpleNamespace(from_path="/es/a", to_path="/es/b", is_active=True),
        SimpleNamespace(from_path="/es/b", to_path="/es/c", is_active=True),
    ]
    assert flatten(rows)[0].to_path == "/es/c"
    for target in ("/es/a", "/es/b"):
        with pytest.raises(ValidationError):
            flatten(
                [
                    SimpleNamespace(from_path="/es/a", to_path="/es/b", is_active=True),
                    SimpleNamespace(from_path="/es/b", to_path=target, is_active=True),
                ]
            )


def test_seo_defaults_and_validation():
    assert public_seo({}, "es") == {"title": "", "description": "", "image": None, "noindex": False}
    assert validate_seo({"title": {"es": "", "en": ""}, "noindex": False}, {}, None) == {}
    for value in (
        {"title": {"es": "a" * 61}},
        {"description": {"en": "x" * 156}},
        {"noindex": "yes"},
        {"unknown": True},
    ):
        with pytest.raises(ValidationError):
            validate_seo(value, {}, None)
    with pytest.raises(PermissionDenied):
        validate_seo({"noindex": True}, {}, None)


def test_missing_pairs_recurses_and_ignores_empty_spanish():
    assert list(
        missing_pairs(
            {
                "title": {"es": "Hola", "en": "Hola"},
                "items": [{"label": {"es": "Enviar", "en": ""}}],
                "empty": {"es": "", "en": ""},
                "complete": {"es": "Sí", "en": "Yes"},
            }
        )
    ) == [("title", "Hola", "Hola"), ("items.0.label", "Enviar", "")]


def test_seo_ratio_and_registry():
    from apps.cms.media import ratios, validate_adjustments
    from apps.cms.registry import export_registry

    assert "1.91:1" in ratios()
    assert export_registry()["seo_slot"]["ratios"] == ("1.91:1",)
    validate_adjustments(0.5, 0.5, {"1.91:1": {"x": 0, "y": 0, "w": 1, "h": 1}}, 1910, 1000)


@pytest.fixture
def owner(db):
    return staff(PROPIETARIO)


def version(key):
    return get_document(key).draft_version


def update(key, row, values, actor):
    with edit_document(key, actor, version(key)):
        visual_documents.mutate(key, "update", {"id": row, "values": values}, actor, None)


@pytest.fixture
def shipping(owner):
    _, actor = owner
    page = Page.objects.filter(kind="shipping").first()
    if page is None:
        page = Page(
            kind="shipping",
            title_es="Envíos",
            title_en="Shipping",
            slug_es="envios",
            slug_en="shipping",
        )
        services.save_page(page, actor=actor, expected_version=version("page:shipping"))
    services.publish_page(page, actor, expected_version=version("page:shipping"))
    return page


@pytest.mark.django_db
def test_slug_publish_chain_restore_and_old_snapshot_immutable(owner, shipping):
    _, actor = owner
    key = "page:shipping"
    original = shipping.revisions.first()
    frozen = deepcopy(original.snapshot)
    old = selectors.page_payload(shipping, "es", original)["alternates"]["es"]
    update(key, "page", {"slug": {"es": " Envíos nuevos "}}, actor)
    assert not Redirect.objects.filter(from_path=old).exists()
    assert selectors.page_payload(shipping, "es", original)["alternates"]["es"] == old
    shipping.refresh_from_db()
    assert shipping.slug_es == "envios-nuevos"
    first = services.publish_page(shipping, actor, expected_version=version(key))
    assert Redirect.objects.get(from_path=old).to_path == "/es/envios-nuevos"
    assert services.publish_page(shipping, actor, expected_version=version(key)).pk == first.pk
    update(key, "page", {"slug": {"es": "envios-finales"}}, actor)
    shipping.refresh_from_db()
    services.publish_page(shipping, actor, expected_version=version(key))
    assert Redirect.objects.get(from_path=old).to_path == "/es/envios-finales"
    assert Redirect.objects.get(from_path="/es/envios-nuevos").to_path == "/es/envios-finales"
    services.restore_page_revision(original, actor, expected_version=version(key))
    assert Redirect.objects.get(from_path=old).is_active
    services.publish_page(shipping, actor, expected_version=version(key))
    assert not Redirect.objects.get(from_path=old).is_active
    assert Redirect.objects.get(from_path="/es/envios-nuevos").to_path == old
    assert Redirect.objects.get(from_path="/es/envios-finales").to_path == old
    original.refresh_from_db()
    assert original.snapshot == frozen


@pytest.mark.django_db
@pytest.mark.parametrize(
    "slug",
    [
        "api",
        "joyeria",
        "jewelry",
        "piezas",
        "pieces",
        "piedras",
        "stones",
        "colecciones",
        "collections",
        "contacto",
        "preview",
        "checkout",
        "dashboard",
        "legal",
    ],
)
def test_reserved_slugs(owner, shipping, slug):
    _, actor = owner
    with pytest.raises(ValidationError):
        update("page:shipping", "page", {"slug": {"es": slug}}, actor)


@pytest.mark.django_db
def test_other_draft_and_published_slug_collisions(owner, shipping):
    _, actor = owner
    other = Page.objects.exclude(pk=shipping.pk).first()
    if not other:
        other = Page.objects.create(kind="privacy", title_es="Privacidad", slug_es="privacidad")
    with pytest.raises(ValidationError):
        update("page:shipping", "page", {"slug": {"es": other.slug_es}}, actor)


@pytest.mark.django_db
def test_redirect_manual_only_existing_internal_and_version(owner, shipping):
    _, actor = owner
    destination = selectors.page_payload(shipping, "es", shipping.revisions.first())["alternates"][
        "es"
    ]
    obj = Redirect(from_path="/es/consulta-anterior", to_path=destination)
    save_redirect(obj, actor, expected_version=version("redirects"))
    assert obj.locale == "es" and obj.origin == "manual"
    with pytest.raises(ContentConflict):
        save_redirect(obj, actor, expected_version=0)
    for source, target in [
        ("/es/falla", "https://evil.test"),
        ("/es/falla", "/es/no-existe"),
        (destination, "/es/joyeria"),
    ]:
        with pytest.raises(ValidationError):
            save_redirect(
                Redirect(from_path=source, to_path=target),
                actor,
                expected_version=version("redirects"),
            )
    obj.is_active = False
    save_redirect(obj, actor, expected_version=version("redirects"))
    assert not Redirect.objects.get(pk=obj.pk).is_active


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,allowed", [(PROPIETARIO, True), (CONTENIDO, False), (OPERACIONES, False)]
)
def test_roles_on_all_new_surfaces(role, allowed):
    browser, actor = staff(role)
    for route in ("cms-translations", "cms-redirect-management"):
        assert browser.get(reverse(route)).status_code == (403 if role == OPERACIONES else 200)
    response = browser.get(reverse("cms-editor-document"), {"document": "menu:main"})
    assert response.status_code == (403 if role == OPERACIONES else 200)
    if not allowed:
        with pytest.raises(PermissionDenied):
            publish_menu("menu:main", actor, expected_version=version("menu:main"))
        with pytest.raises(PermissionDenied):
            save_redirect(
                Redirect(from_path="/es/test", to_path="/es/joyeria"),
                actor,
                expected_version=version("redirects"),
            )
        assert browser.post(reverse("cms-redirect-management"), {}).status_code == 403
        with pytest.raises(PermissionDenied):
            validate_seo({"noindex": True}, {}, actor)
    else:
        assert validate_seo({"noindex": True}, {}, actor)["noindex"]


@pytest.mark.django_db
def test_menu_full_versioned_lifecycle_and_pending(owner):
    _, actor = owner
    key = "menu:main"
    doc = get_document(key)
    initial = doc.menu_publication or publish_menu(key, actor, expected_version=doc.draft_version)
    items = deepcopy(doc.menu_items)
    if not items:
        items = [
            {
                "link": {"kind": "catalog", "label": {"es": "Joyería", "en": "Jewelry"}},
                "visible": True,
            }
        ]
    items[-1]["link"]["label"]["es"] = "Nueva etiqueta"
    update(key, "menu", {"items": items}, actor)
    assert get_document(key).menu_publication_id == initial.pk
    assert pending_changes(key)["count"]
    with pytest.raises(ContentConflict):
        publish_menu(key, actor, expected_version=version(key) - 1)
    published = publish_menu(key, actor, expected_version=version(key))
    assert publish_menu(key, actor, expected_version=version(key)).pk == published.pk
    assert public_menu(key, "es")["items"][-1]["label"] == "Nueva etiqueta"
    restore_menu(initial, actor, expected_version=version(key))
    assert get_document(key).menu_publication_id == published.pk
    restoration = DraftRevision.objects.filter(document__key=key).first()
    assert restoration.restored_from == initial and restoration.snapshot == initial.snapshot
    publish_menu(key, actor, expected_version=version(key))
    assert get_document(key).menu_publication.snapshot == initial.snapshot


@pytest.mark.django_db
def test_menu_external_limits_and_dropdowns(owner):
    link = {
        "link": {
            "kind": "external",
            "label": {"es": "Visitar", "en": "Visit"},
            "url": "https://example.test",
        },
        "visible": True,
    }
    assert validate_items("menu:footer", [link]) == [link]
    with pytest.raises(ValidationError):
        validate_items("menu:main", [link])
    link["link"]["url"] = "http://example.test"
    with pytest.raises(ValidationError):
        validate_items("menu:footer", [link])
    dropdown = {
        "link": {"kind": "stones", "label": {"es": "Piedras", "en": "Stones"}},
        "visible": True,
    }
    assert validate_items("menu:main", [dropdown])
    with pytest.raises(ValidationError):
        validate_items("menu:main", [dropdown] * 9)
    assert menu_groups([dropdown], [])


@pytest.mark.django_db
def test_seo_draft_publish_restore_and_semantic_changes(owner, shipping):
    _, actor = owner
    key = "page:shipping"
    original = shipping.revisions.first()
    update(key, "seo", {"title": {"es": "Envíos seguros", "en": "Safe shipping"}}, actor)
    assert selectors.page_payload(shipping, "es", original)["seo"]["title"] == ""
    assert selectors.page_payload(shipping, "es")["seo"]["title"] == "Envíos seguros"
    assert pending_changes(key)["count"] == 2
    publication = services.publish_page(shipping, actor, expected_version=version(key))
    assert selectors.page_payload(shipping, "en", publication)["seo"]["title"] == "Safe shipping"
    services.restore_page_revision(original, actor, expected_version=version(key))
    assert get_document(key).seo == original.snapshot.get("_seo", {})
    assert selectors.page_payload(shipping, "es", publication)["seo"]["title"] == "Envíos seguros"
    # Home uses a separate frozen SEO field, preserving the historical section array shape.
    first_home = services.publish_home(actor, expected_version=version("home"))
    update(
        "home",
        "seo",
        {"description": {"es": "Desde nuestro taller", "en": "From our workshop"}},
        actor,
    )
    home = services.publish_home(actor, expected_version=version("home"))
    assert selectors.home("en")["seo"]["description"] == "From our workshop"
    assert isinstance(home.snapshot["es"], list)
    services.restore_home(first_home, actor, expected_version=version("home"))
    assert get_document("home").seo == first_home.seo


@pytest.mark.django_db
def test_pending_translation_and_explicit_same_text(owner, shipping):
    browser, actor = owner
    update(
        "page:shipping",
        "page",
        {"title": {"es": "Texto sin traducir", "en": "Texto sin traducir"}},
        actor,
    )
    assert "Texto sin traducir" in str(pending_translations())
    with edit_document("page:shipping", actor, version("page:shipping")):
        visual_documents.mutate(
            "page:shipping", "translation-equal", {"id": "page", "path": "title"}, actor, None
        )
    assert "Texto sin traducir" not in str(pending_translations())
    update("page:shipping", "page", {"title": {"es": "Otro texto", "en": ""}}, actor)
    assert "Otro texto" in str(pending_translations())
    update("page:shipping", "page", {"title": {"en": "Another text"}}, actor)
    assert "Otro texto" not in str(pending_translations())
    assert browser.get(reverse("cms-translations")).status_code == 200


@pytest.mark.django_db
def test_public_redirects_active_cache_headers_and_one_query(django_assert_num_queries):
    from django.core.cache import cache

    cache.clear()
    Redirect.objects.create(from_path="/es/antes", to_path="/es/despues", locale="es")
    Redirect.objects.create(
        from_path="/es/inactiva", to_path="/es/destino", locale="es", is_active=False
    )
    with django_assert_num_queries(1):
        response = Client().get(reverse("cms-redirects"))
    assert response.status_code == 200
    assert response.json() == [
        {"from_path": "/es/antes", "to_path": "/es/despues", "status_code": 301}
    ]
    assert response["Cache-Control"] == "public, max-age=60, s-maxage=60"
    with django_assert_num_queries(0):
        assert Client().get(reverse("cms-redirects")).json() == response.json()
    cache.clear()


@pytest.mark.django_db
def test_public_menu_query_budget_and_csrf(owner, django_assert_max_num_queries):
    browser, _actor = owner
    with django_assert_max_num_queries(6):
        response = Client().get(reverse("cms-menu", args=["main"]))
    assert response.status_code == 200
    assert "items" in response.json()
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = browser.cookies
    assert strict.get(reverse("cms-editor-document") + "?document=menu:main").status_code == 200
    assert (
        strict.post(
            reverse("cms-editor-document") + "?document=menu:main",
            json.dumps({"action": "update"}),
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db(transaction=True)
def test_menu_migration_idempotent_structure_and_safe_reverse():
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    before = [("cms", "0022_menupublication_redirect_and_more")]
    target = [("cms", "0023_initial_menus")]
    module = import_module("apps.cms.migrations.0023_initial_menus")
    try:
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        D, P = apps.get_model("cms", "ContentDocument"), apps.get_model("cms", "MenuPublication")
        D.objects.filter(key__in=["menu:main", "menu:footer"]).delete()
        P.objects.all().delete()
        historical_pages = apps.get_model("cms", "Page")
        revisions = apps.get_model("cms", "PageRevision")
        expected_footer = []
        for kind in ("terms", "privacy", "returns", "shipping", "cookies"):
            page = historical_pages.objects.filter(kind=kind, status="published").first()
            revision = (
                revisions.objects.filter(page_id=page.pk).order_by("-published_at", "-pk").first()
                if page and page.version
                else None
            )
            if revision:
                expected_footer.append(
                    {
                        "link": {
                            "kind": "page",
                            "target": page.pk,
                            "label": {
                                lang: revision.snapshot[lang]["title"] for lang in ("es", "en")
                            },
                        },
                        "visible": True,
                    }
                )
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        apps = executor.loader.project_state(target).apps
        D, P = apps.get_model("cms", "ContentDocument"), apps.get_model("cms", "MenuPublication")
        assert D.objects.get(key="menu:footer").menu_items == expected_footer
        assert D.objects.get(key="menu:main").menu_items == [
            {"link": {"kind": kind, "label": {"es": es, "en": en}}, "visible": True}
            for kind, es, en in module.MAIN
        ]
        with connection.schema_editor() as editor:
            module.seed(apps, editor)
        assert P.objects.count() == 2
        with connection.schema_editor() as editor:
            module.reverse_seed(apps, editor)
        assert P.objects.count() == 0
        with connection.schema_editor() as editor:
            module.seed(apps, editor)
        D.objects.filter(key="menu:main").update(draft_version=1)
        from django.db.migrations.exceptions import IrreversibleError

        with pytest.raises(IrreversibleError), connection.schema_editor() as editor:
            module.reverse_seed(apps, editor)
    finally:
        MigrationExecutor(connection).migrate(leaves)


def test_initial_main_labels_match_existing_dictionary_exactly():
    from pathlib import Path

    root = Path(__file__).resolve().parents[4] / "frontend" / "app" / "[locale]" / "dictionaries"
    if not root.exists():
        pytest.skip("El checkout de backend no incluye los dictionaries del frontend.")
    module = import_module("apps.cms.migrations.0023_initial_menus")
    for index, lang in enumerate(("es", "en")):
        nav = json.loads((root / f"{lang}.json").read_text())["nav"]
        assert [(kind, labels[index]) for kind, *labels in module.MAIN] == [
            (key, nav[key])
            for key in ("catalog", "stones", "collections", "personalize", "story", "contact")
        ]


@pytest.mark.django_db
@pytest.mark.parametrize("role", [CONTENIDO, OPERACIONES])
def test_restore_menu_requires_owner(role):
    _, actor = staff(role)
    publication = MenuPublication.objects.create(menu="main", snapshot=[])
    with pytest.raises(PermissionDenied):
        restore_menu(publication, actor, expected_version=version("menu:main"))


@pytest.mark.django_db
def test_content_edits_menu_and_seo_but_noindex_http_is_denied():
    browser, actor = staff(CONTENIDO)
    key = "menu:main"
    items = [
        {
            "link": {"kind": "catalog", "label": {"es": "Piezas del taller", "en": ""}},
            "visible": True,
        }
    ]
    url = reverse("cms-editor-document")
    response = browser.post(
        url + "?document=" + key,
        json.dumps(
            {
                "action": "update",
                "id": "menu",
                "values": {"items": items},
                "expected_version": version(key),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["version"] == version(key)
    stale = browser.post(
        url + "?document=" + key,
        json.dumps(
            {
                "action": "update",
                "id": "menu",
                "values": {"items": items},
                "expected_version": version(key) - 1,
            }
        ),
        content_type="application/json",
    )
    assert stale.status_code == 409
    update("home", "seo", {"title": {"es": "Nuestro taller", "en": ""}}, actor)
    response = browser.post(
        url + "?document=home",
        json.dumps(
            {
                "action": "update",
                "id": "seo",
                "values": {"noindex": True},
                "expected_version": version("home"),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not get_document("home").seo.get("noindex")
    assert "Piezas del taller" in str(pending_translations())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "target", ["/es/piedras", "/es/piezas", "/en/collections", "/es/pedido", "/es/legal"]
)
def test_redirect_destination_prefix_has_no_page(owner, target):
    _, actor = owner
    with pytest.raises(ValidationError):
        save_redirect(
            Redirect(from_path="/es/origen-inexistente", to_path=target),
            actor,
            expected_version=version("redirects"),
        )


@pytest.mark.django_db
def test_redirect_to_home_and_manual_chains(owner):
    _, actor = owner
    save_redirect(
        Redirect(from_path="/es/primera", to_path="/es/"),
        actor,
        expected_version=version("redirects"),
    )
    assert Redirect.objects.get(from_path="/es/primera").to_path == "/es"
    save_redirect(
        Redirect(from_path="/es/segunda", to_path="/es/primera", status_code=308),
        actor,
        expected_version=version("redirects"),
    )
    assert Redirect.objects.get(from_path="/es/segunda").to_path == "/es"


@pytest.mark.django_db
def test_seo_reference_protects_media_and_requires_share_crop(owner):
    from apps.cms.media import all_usage, used_by
    from apps.cms.models import MediaAsset

    _, actor = owner
    asset = MediaAsset.objects.create(
        original="cms/share.webp",
        state="ready",
        version=1,
        alt_es="Taller",
        alt_en="Workshop",
        versions={
            "1": {
                "1.91:1": {
                    "src": "/media/share.webp",
                    "srcset": "",
                    "width": 1200,
                    "height": 628,
                    "alt": {"es": "Taller", "en": "Workshop"},
                }
            }
        },
    )
    ref = {"asset": asset.pk, "crop": "1.91:1", "version": 1}
    update("home", "seo", {"image": ref}, actor)
    assert used_by(asset, all_usage())
    services.publish_home(actor, expected_version=version("home"))
    update("home", "seo", {"image": None}, actor)
    assert any(row["state"] == "Publicado" for row in used_by(asset, all_usage()))
    with pytest.raises(ValidationError):
        update("home", "seo", {"image": {**ref, "crop": "4:5"}}, actor)


@pytest.mark.django_db
def test_personalize_historical_body_is_hidden_until_explicit_edit(owner):
    _, actor = owner
    page, _ = Page.objects.get_or_create(
        kind="personalize",
        defaults={"title_es": "Personaliza", "slug_es": "personaliza", "slug_en": "customize"},
    )
    page.body_enabled = False
    page.body_es = "Contenido general anterior"
    page.save()
    original = services.publish_page(page, actor, expected_version=version("page:personalize"))
    assert not selectors.page_payload(page, "es", original)["body_visible"]
    update("page:personalize", "seo", {"title": {"es": "Una joya para ti"}}, actor)
    seo_only = services.publish_page(page, actor, expected_version=version("page:personalize"))
    assert not selectors.page_payload(page, "es", seo_only)["body_visible"]
    update(
        "page:personalize",
        "page",
        {"body": {"es": "Una bienvenida escrita para esta página"}},
        actor,
    )
    assert selectors.page_payload(Page.objects.get(pk=page.pk), "es")["body_visible"]
    services.publish_page(page, actor, expected_version=version("page:personalize"))
    services.restore_page_revision(original, actor, expected_version=version("page:personalize"))
    page.refresh_from_db()
    assert not page.body_enabled


@pytest.mark.django_db
def test_restored_empty_english_slug_keeps_its_effective_path(owner, shipping):
    browser, actor = owner
    shipping.slug_en = ""
    shipping.save()
    original = services.publish_page(shipping, actor, expected_version=version("page:shipping"))
    english = selectors.page_payload(shipping, "en", original)["alternates"]["en"]
    services.restore_page_revision(original, actor, expected_version=version("page:shipping"))
    update("page:shipping", "page", {"slug": {"es": "envios-en-otra-direccion"}}, actor)
    publication = services.publish_page(shipping, actor, expected_version=version("page:shipping"))
    payload = selectors.page_payload(shipping, "en", publication)
    assert payload["alternates"]["en"] == english
    assert (
        Client().get(reverse("cms-page", args=[payload["slug"]]), {"locale": "en"}).status_code
        == 200
    )
    from apps.cms.preview import make_token

    assert (
        browser.get(
            reverse("cms-page", args=[payload["slug"]]),
            {"locale": "en", "preview": make_token(actor)},
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "kind",
    [
        "terms",
        "privacy",
        "returns",
        "shipping",
        "cookies",
        "manufacturer",
        "contact",
        "personalize",
    ],
)
def test_legacy_pending_changes_zero_for_every_page_type(kind, monkeypatch):
    """Old immutable publications lack additive headings/SEO, but own their section titles."""
    from apps.cms import documents, models
    from apps.cms.review_changes import page_groups

    current = {"_seo": {}, "_body_enabled": False}
    for lang in ("es", "en"):
        current[lang] = {
            "source": {
                "title": f"Title {lang}",
                "body": "Body",
                "slug": f"slug-{lang}",
                "process_title": f"Process {lang}",
                "faq_title": f"FAQ {lang}",
            },
            "process": {"title": f"Process {lang}", "steps": []},
            "faq": {"title": f"FAQ {lang}", "items": []},
        }
    old = deepcopy(current)
    old.pop("_seo")
    old.pop("_body_enabled")
    for lang in ("es", "en"):
        for field in ("process_title", "faq_title"):
            old[lang]["source"].pop(field)
    frozen = deepcopy(old)
    page = SimpleNamespace(
        kind=kind, revisions=SimpleNamespace(first=lambda: SimpleNamespace(snapshot=old))
    )
    monkeypatch.setattr(documents, "get_document", lambda key: SimpleNamespace(seo={}))
    monkeypatch.setattr(models.Page.objects, "get", lambda **kwargs: page)
    monkeypatch.setattr(services, "page_snapshot", lambda page: current)
    assert pending_changes(f"page:{kind}")["count"] == 0
    assert old == frozen
    changed = deepcopy(current)
    changed["es"]["source"]["body"] = "Real edit"
    assert page_groups(changed, old, kind=kind)
    changed = deepcopy(current)
    changed["es"]["source"]["process_title"] = "New process"
    assert bool(page_groups(changed, old, kind=kind)) == (kind == "personalize")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kind",
    [
        "terms",
        "privacy",
        "returns",
        "shipping",
        "cookies",
        "manufacturer",
        "contact",
        "personalize",
    ],
)
def test_legacy_page_revision_has_no_phantom_pending_changes(owner, kind):
    from apps.cms.models import PageRevision

    _, actor = owner
    page = Page.objects.get(kind=kind)
    snapshot = services.page_snapshot(page)
    snapshot.pop("_seo")
    snapshot.pop("_body_enabled")
    for lang in ("es", "en"):
        snapshot[lang].pop("path", None)
        for field in ("process_title", "faq_title"):
            snapshot[lang].pop(field, None)
            snapshot[lang].get("source", {}).pop(field, None)
    PageRevision.objects.create(
        page=page, version=page.version + 1, snapshot=snapshot, published_by=actor
    )
    assert pending_changes(f"page:{kind}")["count"] == 0
    if kind != "personalize":
        assert selectors.page_payload(page, "es")["body_visible"] is True
