from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from PIL import Image
from rest_framework.request import Request

from apps.accounts.models import User
from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO, ROLE_PERMISSIONS
from apps.audit.models import AuditLog
from apps.catalog.api.serializers import PieceListSerializer
from apps.catalog.models import Category, Collection, CollectionPiece, Piece, Stone
from apps.cms import selectors, services
from apps.cms.admin import HomeSectionAdmin, PageAdmin, PublicationAdmin
from apps.cms.models import HomePublication, HomeSection, Page, PageRevision, PersonalizationService
from apps.cms.preview import PreviewInvalid, make_token, verify_token
from apps.cms.tests.helpers import cms_version
from apps.core.api.base import PublicReadThrottle, PublicView
from apps.core.routes import href
from apps.core.selectors import get_solo

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor() -> User:
    return User.objects.create_user(
        username="editor", email="editor@example.com", is_staff=True, is_superuser=True
    )


@pytest.fixture(autouse=True)
def reset_cache(settings: Any, tmp_path: Path) -> None:
    cache.clear()
    settings.MEDIA_ROOT = tmp_path


def clean_home() -> None:
    HomeSection.objects.all().delete()


def section(**kwargs: Any) -> HomeSection:
    defaults = {"kind": "hero", "title_es": "Tierra", "title_en": "Earth"}
    return HomeSection.objects.create(**(defaults | kwargs))


def get(client: Client, path: str, **params: Any) -> Any:
    return client.get(f"/api/v1/{path}", params)


@pytest.mark.parametrize(
    ("key", "es", "en"),
    [
        ("home", "/es", "/en"),
        ("catalog", "/es/joyeria", "/en/jewelry"),
        ("category", "/es/joyeria/anillo", "/en/jewelry/ring"),
        ("stone", "/es/piedras/anillo", "/en/stones/ring"),
        ("collection", "/es/colecciones/anillo", "/en/collections/ring"),
        ("piece", "/es/piezas/anillo", "/en/pieces/ring"),
        ("personalize", "/es/personaliza", "/en/customize"),
        ("story", "/es/historia", "/en/story"),
        ("contact", "/es/contacto", "/en/contact"),
        ("wishlist", "/es/deseos", "/en/wishlist"),
        ("search", "/es/buscar", "/en/search"),
        ("page", "/es/legal/anillo", "/en/legal/ring"),
    ],
)
def test_routes(key: str, es: str, en: str) -> None:
    obj = SimpleNamespace(slug_es="anillo", slug_en="ring")
    assert href(key, "es", obj) == es
    assert href(key, "en", obj) == en
    obj.slug_en = ""
    assert href(key, "en", obj) == en.replace("ring", "anillo")


@pytest.mark.parametrize(
    "kind", ["hero", "statement", "stone_panels", "category_grid", "story", "personalize", "banner"]
)
def test_valid_section_kinds(cms_actor, kind: str) -> None:
    services.save_section(
        HomeSection(kind=kind, title_es="Título"),
        expected_version=cms_version(HomeSection(kind=kind, title_es="Título")),
        actor=cms_actor,
    )


@pytest.mark.parametrize("target", ["category", "stone", "collection", "piece", "page", "external"])
def test_invalid_cta_target(cms_actor, target: str) -> None:
    with pytest.raises(ValidationError):
        services.save_section(
            HomeSection(kind="hero", cta_kind=target, cta_label_es="Ver"),
            expected_version=cms_version(
                HomeSection(kind="hero", cta_kind=target, cta_label_es="Ver")
            ),
            actor=cms_actor,
        )


def test_rail_requires_collection(cms_actor) -> None:
    with pytest.raises(ValidationError):
        services.save_section(
            HomeSection(kind="collection_rail"),
            expected_version=cms_version(HomeSection(kind="collection_rail")),
            actor=cms_actor,
        )


def test_cta_localized_and_external(cms_actor, actor: User, client: Client) -> None:
    clean_home()
    category = Category.objects.create(name_es="Anillos", slug_es="anillos", slug_en="rings")
    section(cta_kind="category", cta_category=category, cta_label_es="Ver", cta_label_en="View")
    section(
        position=1,
        cta_kind="external",
        cta_external_url="https://example.com",
        cta_label_es="Visitar",
    )
    services.publish_home(actor, expected_version=cms_version())
    data = get(client, "cms/home", locale="en").json()["sections"]
    assert data[0]["cta"] == {"label": "View", "href": "/en/jewelry/rings", "external": False}
    assert data[1]["cta"]["external"] is True
    with pytest.raises(ValidationError):
        services.save_section(
            HomeSection(
                kind="hero",
                cta_kind="external",
                cta_external_url="http://example.com",
                cta_label_es="Ver",
            ),
            expected_version=cms_version(
                HomeSection(
                    kind="hero",
                    cta_kind="external",
                    cta_external_url="http://example.com",
                    cta_label_es="Ver",
                )
            ),
            actor=cms_actor,
        )


def test_home_snapshot_restore_and_preview(cms_actor, actor: User, client: Client) -> None:
    clean_home()
    obj = section()
    section(is_visible=False, position=10)
    assert get(client, "cms/home").json() == {
        "sections": [],
        "seo": {"title": "", "description": "", "image": None, "noindex": False},
        "published_at": None,
        "preview": False,
    }
    first = services.publish_home(actor, note="Inicial", expected_version=cms_version())
    obj.title_es = "Borrador nuevo"
    services.save_section(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert get(client, "cms/home").json()["sections"][0]["title"] == "Tierra"
    preview = get(client, "cms/home", preview=make_token(actor))
    assert preview.json()["preview"] is True
    assert preview.json()["sections"][0]["title"] == "Borrador nuevo"
    assert preview["Cache-Control"] == "private, no-store"
    services.restore_home(first, actor, expected_version=cms_version())
    assert HomeSection.objects.count() == 2
    assert HomeSection.objects.first().title_es == "Tierra"  # type: ignore[union-attr]
    assert HomePublication.objects.count() == 1
    services.publish_home(actor, expected_version=cms_version())
    assert get(client, "cms/home").json()["sections"][0]["title"] == "Tierra"
    assert set(
        AuditLog.objects.filter(action__startswith="cms.home_").values_list("action", flat=True)
    ) == {"cms.home_published", "cms.home_restored"}


def test_live_rail_stones_and_bounded_queries(actor: User, client: Client) -> None:
    clean_home()
    collection = Collection.objects.create(name_es="Selección", slug_es="seleccion")
    piece = Piece.objects.create(
        sku="CMS-1", name_es="Pieza", slug_es="pieza", price_cents=12000, status="published"
    )
    hidden = Piece.objects.create(
        sku="CMS-2", name_es="Oculta", slug_es="oculta", price_cents=12000, status="hidden"
    )
    for obj in (piece, hidden):
        CollectionPiece.objects.create(collection=collection, piece=obj)
    section(kind="collection_rail", collection=collection)
    section(kind="stone_panels", position=1)
    services.publish_home(actor, expected_version=cms_version())
    Stone.objects.create(
        name_es="Diamante", name_en="Diamond", slug_es="diamante", slug_en="diamond"
    )
    first = get(client, "cms/home").json()["sections"]
    assert first[0]["pieces"] == [dict(PieceListSerializer(piece).data)]
    assert first[1]["stones"][0]["href"] == "/es/piedras/diamante"
    with CaptureQueriesContext(connection) as one:
        get(client, "cms/home")
    for i in range(20):
        section(kind="collection_rail", collection=collection, position=i + 2)
        section(kind="stone_panels", position=i + 30)
    services.publish_home(actor, expected_version=cms_version())
    with CaptureQueriesContext(connection) as many:
        response = get(client, "cms/home")
    assert len(one) == len(many)
    assert len(many) <= 9
    assert len(response.json()["sections"]) == 42
    Piece.objects.filter(pk=piece.pk).update(sale_state="sold")
    assert get(client, "cms/home").json()["sections"][0]["pieces"] == []
    assert "collection_id" not in first[0]


def test_rail_order_and_limit(actor: User, client: Client) -> None:
    clean_home()
    collection = Collection.objects.create(name_es="Selección", slug_es="seleccion")
    for i in range(10):
        piece = Piece.objects.create(
            sku=f"CMS-{i}",
            name_es=f"Pieza {i}",
            slug_es=f"pieza-{i}",
            price_cents=100,
            status="published",
        )
        CollectionPiece.objects.create(collection=collection, piece=piece, position=10 - i)
    section(kind="collection_rail", collection=collection)
    services.publish_home(actor, expected_version=cms_version())
    cards = get(client, "cms/home").json()["sections"][0]["pieces"]
    assert len(cards) == 8
    assert cards[0]["sku"] == "CMS-9"


def test_preview_valid_tampered_and_user_state(actor: User, client: Client) -> None:
    token = make_token(actor)
    assert verify_token(token) == actor
    assert get(client, "cms/preview/verify", token=token).json()["user"] == "editor"
    for value in ("", token + "x", "broken"):
        response = get(client, "cms/home", preview=value)
        assert response.status_code == 403
        assert response.json()["code"] == "preview_invalid"
        assert response["Content-Type"] == "application/problem+json"
    actor.is_staff = False
    actor.save()
    with pytest.raises(PreviewInvalid):
        verify_token(token)
    actor.is_staff = True
    actor.is_active = False
    actor.save()
    with pytest.raises(PreviewInvalid):
        verify_token(token)


def test_preview_expired(actor: User) -> None:
    with patch("django.core.signing.time.time", return_value=1000):
        token = make_token(actor)
    with patch("django.core.signing.time.time", return_value=1601), pytest.raises(PreviewInvalid):
        verify_token(token)


def test_page_publication_restore_and_alternates(cms_actor, actor: User, client: Client) -> None:
    page = Page.objects.get(kind="terms")
    assert get(client, "cms/pages/terminos").status_code == 404
    page.body_es = "## Términos\n\n**Texto**"
    services.save_page(page, expected_version=cms_version(page), actor=cms_actor)
    first = services.publish_page(page, actor, expected_version=cms_version(page))
    assert page.version == 1
    page.body_es = "Nuevo borrador"
    page.slug_es = "terminos-nuevos"
    services.save_page(page, expected_version=cms_version(page), actor=cms_actor)
    public = get(client, "cms/pages/terminos").json()
    assert public["body_html"] == "<h2>Términos</h2>\n<p><strong>Texto</strong></p>"
    assert public["alternates"] == {"es": "/es/legal/terminos", "en": "/en/legal/terms"}
    assert get(client, "cms/pages/terminos-nuevos").status_code == 404
    assert (
        get(client, "cms/pages/terminos-nuevos", preview=make_token(actor)).json()["body_html"]
        == "<p>Nuevo borrador</p>"
    )
    services.publish_page(page, actor, expected_version=cms_version(page))
    assert page.version == 2
    services.restore_page_revision(first, actor, expected_version=cms_version(first))
    page.refresh_from_db()
    assert page.slug_es == "terminos"
    assert page.version == 2
    assert get(client, "cms/pages/terminos-nuevos").status_code == 200
    assert PageRevision.objects.filter(page=page).count() == 2
    assert set(
        AuditLog.objects.filter(action__startswith="cms.page_").values_list("action", flat=True)
    ) == {"cms.page_published", "cms.page_restored"}


@pytest.mark.parametrize(
    ("kind", "path"),
    [("manufacturer", "/en/story"), ("contact", "/en/contact"), ("personalize", "/en/customize")],
)
def test_fixed_page_routes(cms_actor, kind: str, path: str, actor: User, client: Client) -> None:
    page = Page.objects.get(kind=kind)
    page.slug_en = ""
    services.save_page(page, expected_version=cms_version(page), actor=cms_actor)
    services.publish_page(page, actor, expected_version=cms_version(page))
    payload = get(client, f"cms/pages/kind/{kind}", locale="en").json()
    assert payload["alternates"]["en"] == path
    assert payload["slug"] == page.slug_es


@pytest.mark.parametrize("method", ["save", "delete", "update", "queryset_delete", "bulk_update"])
def test_revisions_immutable(method: str, actor: User) -> None:
    revision = services.publish_page(
        Page.objects.get(kind="privacy"),
        actor,
        expected_version=cms_version(Page.objects.get(kind="privacy")),
    )
    with pytest.raises(ValidationError):
        if method == "save":
            revision.save()
        elif method == "delete":
            revision.delete()
        elif method == "update":
            PageRevision.objects.filter(pk=revision.pk).update(version=99)
        elif method == "queryset_delete":
            PageRevision.objects.filter(pk=revision.pk).delete()
        else:
            PageRevision.objects.bulk_update([revision], ["version"])


def test_home_publications_immutable(actor: User) -> None:
    publication = services.publish_home(actor, expected_version=cms_version())
    with pytest.raises(ValidationError):
        publication.save()
    with pytest.raises(ValidationError):
        HomePublication.objects.all().update(note="edit")
    with pytest.raises(ValidationError):
        HomePublication.objects.all().delete()


@pytest.mark.parametrize(
    "source",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "[click](javascript:alert(1))",
        "[click](data:text/html,evil)",
        '<a href="javascript:alert(1)" onclick="alert(1)">click</a>',
        "[click](//evil.example/x)",
        "[click](http://example.com)",
    ],
)
def test_markdown_xss(source: str) -> None:
    result = services.render_markdown(source)
    assert "<script" not in result
    assert "<img" not in result
    assert '<a href="javascript:' not in result
    assert '<a href="data:' not in result
    assert '<a href="//' not in result
    assert '<a href="http:' not in result
    if source.startswith("<"):
        assert "&lt;" in result


def test_markdown_allowlist() -> None:
    result = services.render_markdown(
        "## Heading\n\n**Bold** *em*\n\n- One\n- Two\n\n"
        "[web](https://example.com) [mail](mailto:a@example.com) "
        "[relative](/es/contacto)\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    )
    assert "<h2>Heading</h2>" in result
    assert "<ul>" in result
    assert "<table>" in result
    assert 'rel="noopener noreferrer"' in result
    assert 'href="mailto:a@example.com"' in result
    assert 'href="/es/contacto"' in result
    assert "<strong>Bold</strong>" in result


def test_personalization_and_settings(cms_actor, actor: User, client: Client) -> None:
    assert get(client, "cms/personalization").json() == {"services": []}
    service = PersonalizationService.objects.first()
    assert service is not None
    service.is_active = True
    service.whatsapp_message_es = "Quiero {service}. {url}"
    services.save_personalization(service, actor=cms_actor)
    assert get(client, "cms/personalization").json()["services"][0]["whatsapp_url"] is None
    config = get_solo()
    config.whatsapp_number = "573001234567"
    config.instagram_url = "https://instagram.com/serti"
    config.support_email = "help@example.com"
    config.save()
    service_data = get(client, "cms/personalization").json()["services"][0]
    assert len(get(client, "cms/personalization").json()["services"]) == 1
    message = parse_qs(urlparse(service_data["whatsapp_url"]).query)["text"][0]
    assert service.title in message and "/es/personaliza" in message
    for kind in ("cookies", "returns", "privacy", "terms", "shipping"):
        services.publish_page(
            Page.objects.get(kind=kind),
            actor,
            expected_version=cms_version(Page.objects.get(kind=kind)),
        )
    data = get(client, "site/settings", locale="en").json()
    assert data["social"] == [{"network": "instagram", "url": config.instagram_url}]
    assert data["support_email"] == "help@example.com"
    assert data["whatsapp"]["number"] == "573001234567"
    assert [page["kind"] for page in data["legal_pages"]] == [
        "terms",
        "privacy",
        "returns",
        "shipping",
        "cookies",
    ]
    assert data["legal_pages"][0]["href"] == "/en/legal/terms"


@pytest.mark.parametrize(
    "template", ["{name}", "{service.__class__}", "{url[0]}", "{service!r}", "{service:20}", "{"]
)
def test_personalization_template_rejected(cms_actor, template: str) -> None:
    service = PersonalizationService(title_es="Grabado", whatsapp_message_es=template)
    with pytest.raises(ValidationError):
        services.save_personalization(service, actor=cms_actor)


@pytest.mark.parametrize("network", ["instagram", "facebook", "tiktok", "pinterest"])
def test_social_https(network: str) -> None:
    config = get_solo()
    setattr(config, f"{network}_url", "http://example.com")
    with pytest.raises(ValidationError):
        config.full_clean()


@pytest.mark.parametrize(
    ("configured", "supplied", "exempt"),
    [("secret", "secret", True), ("secret", "bad", False), ("secret", "", False), ("", "", False)],
)
def test_throttle(configured: str, supplied: str, exempt: bool, settings: Any) -> None:
    settings.INTERNAL_API_TOKEN = configured
    settings.PUBLIC_READ_RATE = "3/min"
    request = Request(RequestFactory().get("/api/v1/cms/home", HTTP_X_INTERNAL_TOKEN=supplied))
    results = [PublicReadThrottle().allow_request(request, PublicView()) for _ in range(500)]
    assert all(results) if exempt else sum(results) == 3


@pytest.mark.parametrize("role", [PROPIETARIO, CONTENIDO, OPERACIONES])
def test_roles_and_service_permissions(role: str) -> None:
    user = User.objects.create_user(username=role, email=f"{role}@example.com", is_staff=True)
    group = Group.objects.get(name=role)
    for permission in ROLE_PERMISSIONS[role]:
        app, codename = permission.split(".")
        group.permissions.add(
            Permission.objects.get(content_type__app_label=app, codename=codename)
        )
    user.groups.add(group)
    for model in ("homesection", "page", "personalizationservice"):
        assert user.has_perm(f"cms.view_{model}") == (role != OPERACIONES)
        assert user.has_perm(f"cms.change_{model}") == (role != OPERACIONES)
        assert user.has_perm(f"cms.add_{model}") == (role != OPERACIONES)
    assert user.has_perm("cms.publish_content") == (role == PROPIETARIO)
    if role != PROPIETARIO:
        with pytest.raises(PermissionDenied):
            services.publish_home(user, expected_version=cms_version())
    else:
        services.publish_home(user, expected_version=cms_version())


def test_admin_preview_and_actions(actor: User) -> None:
    from django.contrib import admin

    request = RequestFactory().get("/")
    request.user = actor
    home_admin = HomeSectionAdmin(HomeSection, admin.site)
    target = home_admin.preview(request)["Location"]
    query = parse_qs(urlparse(target).query)
    assert query["path"] == ["/es"]
    assert verify_token(query["token"][0]) == actor
    page = Page.objects.get(kind="manufacturer")
    page_admin = PageAdmin(Page, admin.site)
    assert parse_qs(urlparse(page_admin.preview(request, page.pk)["Location"]).query)["path"] == [
        "/es/historia"
    ]
    user = User.objects.create_user(username="reader", email="reader@example.com", is_staff=True)
    request.user = user
    assert "publish" not in page_admin.get_actions(request)
    publication_admin = PublicationAdmin(HomePublication, admin.site)
    assert "restore" not in publication_admin.get_actions(request)
    with pytest.raises(PermissionDenied):
        home_admin.preview(request)
    with pytest.raises(PermissionDenied):
        home_admin.publish(request)


def test_image_pipeline(cms_actor, actor: User, tmp_path: Path) -> None:
    output = BytesIO()
    Image.new("RGB", (1920, 1200), "red").save(output, "PNG")
    obj = HomeSection(
        kind="hero",
        image=ContentFile(output.getvalue(), name="upload.png"),
        image_alt_es="Rojo",
        image_alt_en="Red",
    )
    services.save_section(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert (obj.width, obj.height) == (1920, 1080)
    assert set(obj.renditions["webp"]) == {"960", "1600", "1920"}  # source width kept
    assert obj.image.name and obj.image.name.endswith(".webp")
    for width, name in obj.renditions["webp"].items():
        with Image.open(tmp_path / name) as image:
            assert image.format == "WEBP"
            assert image.width == int(width)
            assert not image.getexif()
    payload = selectors.image_data(obj, "en")
    assert payload is not None
    assert payload["src"].startswith("/media/")
    assert payload["alt"] == "Red"
    original = obj.image.name
    services.save_section(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert obj.image.name == original
    bad = HomeSection(
        kind="hero",
        image=ContentFile(b"<svg></svg>", name="bad.svg"),
        image_alt_es="SVG",
        image_alt_en="SVG",
    )
    with pytest.raises(ValidationError):
        services.save_section(bad, expected_version=cms_version(bad), actor=cms_actor)


@pytest.mark.parametrize(
    "kind,size", [("hero", (1200, 675)), ("story", (960, 1200)), ("personalize", (960, 1200))]
)
def test_section_images_match_the_frame_they_are_shown_in(
    cms_actor, actor: User, tmp_path: Path, kind: str, size: tuple[int, int]
) -> None:
    # The same square photo becomes landscape for the hero and portrait for editorial frames.
    output = BytesIO()
    Image.new("RGB", (1200, 1200), "red").save(output, "PNG")
    obj = HomeSection(
        kind=kind,
        title_es="T",
        image=ContentFile(output.getvalue(), name="upload.png"),
        image_alt_es="Rojo",
        image_alt_en="Red",
    )
    services.save_section(obj, expected_version=cms_version(obj), actor=cms_actor)
    assert (obj.width, obj.height) == size


def test_seed_content() -> None:
    assert Page.objects.count() == 8
    # 0013 publishes Personaliza with its seeded steps/FAQ so the store does not change.
    assert set(Page.objects.exclude(status="draft").values_list("kind", flat=True)) == {
        "personalize"
    }
    assert PersonalizationService.objects.count() == 5
    assert not PersonalizationService.objects.filter(is_active=True).exists()
    assert HomeSection.objects.filter(kind="hero").exists()
    assert not HomePublication.objects.exists()


def test_draft_query_count(actor: User, client: Client) -> None:
    clean_home()
    section()
    token = make_token(actor)
    with CaptureQueriesContext(connection) as one:
        assert get(client, "cms/home", preview=token).status_code == 200
    for i in range(30):
        section(position=i + 1)
    with CaptureQueriesContext(connection) as many:
        assert get(client, "cms/home", preview=token).status_code == 200
    assert len(many) == len(one) == 4


def test_empty_markdown_and_raw_source_restore(cms_actor, actor: User, client: Client) -> None:
    page = Page.objects.get(kind="contact")
    page.body_es = ""
    page.body_en = ""
    page.title_en = ""
    services.save_page(page, expected_version=cms_version(page), actor=cms_actor)
    revision = services.publish_page(page, actor, expected_version=cms_version(page))
    assert get(client, "cms/pages/kind/contact", locale="en").json()["body_html"] == ""
    services.restore_page_revision(revision, actor, expected_version=cms_version(revision))
    page.refresh_from_db()
    assert page.title_en == ""


def test_settings_without_number_or_published_pages(client: Client) -> None:
    data = get(client, "site/settings").json()
    assert data == {
        "whatsapp": {"number": None, "general_url": None},
        "social": [],
        "support_email": None,
        "legal_pages": [],
        "legal_versions": {"terms": None, "privacy": None},
        "certificate_price_cents": 0,
        "title_scale": 1.0,
        "text_scale": 1.0,
    }


def test_admin_forms_reject_invalid_content() -> None:
    from django.contrib import admin

    model_admin: Any = admin.site._registry[HomeSection]
    request = RequestFactory().get("/")
    request.user = User(is_staff=True, is_superuser=True, is_active=True)
    form_class = model_admin.get_form(request)
    form = form_class(
        data={
            "expected_version": cms_version(),
            "kind": "collection_rail",
            "position": 0,
            "is_visible": True,
            "cta_kind": "none",
        }
    )
    assert not form.is_valid()
    assert "colección" in str(form.errors)


def test_schema_documents_cms_contract() -> None:
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)  # type: ignore[no-untyped-call]
    assert schema is not None
    for path in (
        "cms/home",
        "cms/pages/{slug}",
        "cms/pages/kind/{kind}",
        "cms/personalization",
        "cms/preview/verify",
        "site/settings",
    ):
        operation = schema["paths"][f"/api/v1/{path}"]["get"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"]
    components = schema["components"]["schemas"]
    assert components["Home"]["properties"]["sections"]["items"]["$ref"].endswith("HomeSection")
    assert set(components["HomeSection"]["discriminator"]["mapping"]) == {
        "hero",
        "statement",
        "stone_panels",
        "collection_rail",
        "category_grid",
        "story",
        "personalize",
        "banner",
        "image_text",
        "faq",
        "process",
    }


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_page_publications_are_idempotent(actor: User) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    page, _ = Page.objects.get_or_create(
        kind="terms", defaults={"title_es": "Términos", "slug_es": "terminos"}
    )
    page_id, user_id, initial_version = page.pk, actor.pk, page.version
    barrier = Barrier(2)

    def publish(_: int) -> int:
        close_old_connections()
        try:
            user = User.objects.get(pk=user_id)
            draft = Page.objects.get(pk=page_id)
            barrier.wait(timeout=10)
            return services.publish_page(draft, user, expected_version=cms_version(draft)).version
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = list(pool.map(publish, range(2)))
    assert versions[0] == versions[1]
    assert PageRevision.objects.filter(page_id=page_id).count() <= initial_version + 1


def test_publisher_can_be_deleted_and_history_keeps_their_name(actor: User) -> None:
    from apps.cms.models import HomePublication, Page, PageRevision

    publication = services.publish_home(actor, expected_version=cms_version())
    revision = services.publish_page(
        Page.objects.get(kind="terms"),
        actor,
        expected_version=cms_version(Page.objects.get(kind="terms")),
    )
    username = actor.get_username()
    actor.delete()
    publication = HomePublication.objects.get(pk=publication.pk)
    revision = PageRevision.objects.get(pk=revision.pk)
    assert publication.published_by is None and publication.published_by_repr == username
    assert revision.published_by is None and revision.published_by_repr == username
