"""Add library references without touching files or immutable publications."""
import hashlib
from copy import deepcopy
from urllib.parse import urlsplit
from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError


def migrate_media(apps, schema_editor):
    alias = schema_editor.connection.alias
    Asset = apps.get_model("cms", "MediaAsset")
    media_url = settings.MEDIA_URL

    def import_image(path, payload, ratio, width=0, height=0):
        if not path or not path.startswith("cms/"):
            return None
        digest = hashlib.sha256(("legacy:" + path + repr(payload)).encode()).hexdigest()
        source_hash = None
        size = 0
        root = Path(settings.MEDIA_ROOT).resolve()
        file = (root / path).resolve()
        if file.is_relative_to(root / "cms") and file.is_file() and file.stat().st_size <= 25 * 1024 * 1024:
            size = file.stat().st_size
            actual_hash = hashlib.sha256(file.read_bytes()).hexdigest()
            if not Asset.objects.using(alias).filter(sha256=actual_hash).exists():
                source_hash = actual_hash
        asset, _ = Asset.objects.using(alias).get_or_create(legacy_fingerprint=digest, defaults={
            "sha256": source_hash, "size": size,
            "original": path, "legacy_key": path, "width": width or payload.get("width", 0),
            "height": height or payload.get("height", 0), "version": 0, "state": "ready",
            "alt_es": payload["alt"].get("es", ""), "alt_en": payload["alt"].get("en", ""),
            "versions": {"0": {ratio: payload}},
        })
        return {"asset": asset.pk, "crop": ratio, "version": 0}

    for name in ("HomeSection", "HeroSlide", "PersonalizationService"):
        Model = apps.get_model("cms", name)
        for row in Model.objects.using(alias).all().iterator():
            if row.image and row.image.name.startswith("cms/") and not row.image_reference:
                paths = row.renditions.get("webp", {})
                chosen = paths.get("960") or (paths[max(paths, key=int)] if paths else row.image.name)
                alt = "alt" if name == "HeroSlide" else "image_alt"
                payload = {
                    "src": media_url + chosen,
                    "srcset": ", ".join(f"{media_url}{p} {w}w" for w, p in sorted(paths.items(), key=lambda item: int(item[0]))),
                    "width": row.width, "height": row.height,
                    "alt": {lang: getattr(row, f"{alt}_{lang}", "") or getattr(row, f"{alt}_es", "") or "" for lang in ("es", "en")},
                }
                ratio = "16:9" if (getattr(row, "kind", "") == "hero" or getattr(row, "device", "") == "desktop") else "4:5"
                row.image_reference = import_image(row.image.name, payload, ratio)
                row.save(update_fields=["image_reference"])
            if name == "HomeSection" and row.props:
                props = deepcopy(row.props)
                changed = False
                for key in ("image", "mobile_image"):
                    value = props.get(key)
                    if isinstance(value, dict) and "src" in value and value["src"].startswith(media_url + "cms/"):
                        path = urlsplit(value["src"]).path[len(media_url):]
                        props[key] = import_image(path, value, "4:5")
                        changed = True
                if changed:
                    row.props = props
                    row.save(update_fields=["props"])

    # Import history-only CMS images as well, but never rewrite frozen snapshots.
    history_images = {}
    def walk(value, locale="es"):
        if isinstance(value, dict):
            # Hidden historical sections may only have editable FileField sources.
            for key, prefix in (("image", ""), ("image_mobile", "mobile_")):
                path = value.get(key)
                if isinstance(path, str) and path.startswith("cms/"):
                    paths = value.get(prefix + "renditions", {}).get("webp", {})
                    chosen = paths.get("960") or (paths[max(paths, key=int)] if paths else path)
                    alt_key = "image_alt" if "image_alt_es" in value else "alt"
                    payload = {
                        "src": media_url + chosen,
                        "srcset": ", ".join(f"{media_url}{p} {w}w" for w, p in sorted(paths.items(), key=lambda item: int(item[0]))),
                        "width": value.get(prefix + "width", 0),
                        "height": value.get(prefix + "height", 0),
                        "alt": {lang: value.get(f"{alt_key}_{lang}") or value.get(f"{alt_key}_es") or "" for lang in ("es", "en")},
                    }
                    if not Asset.objects.using(alias).filter(legacy_key=path).exists():
                        import_image(path, payload, "4:5")
            if isinstance(value.get("src"), str) and value["src"].startswith(media_url + "cms/"):
                image = history_images.setdefault(value["src"], deepcopy(value))
                if not isinstance(image.get("alt"), dict):
                    image["alt"] = {}
                alt = value.get("alt", "")
                image["alt"][locale] = alt.get(locale, "") if isinstance(alt, dict) else alt
            for key, item in value.items():
                walk(item, key if key in ("es", "en") else locale)
        elif isinstance(value, list):
            for item in value:
                walk(item, locale)
    for name in ("HomePublication", "PageRevision", "DraftRevision"):
        for row in apps.get_model("cms", name).objects.using(alias).all().iterator():
            walk(row.snapshot)
            walk(getattr(row, "draft_snapshot", {}))
    for value in history_images.values():
        value = {key: value.get(key, default) for key, default in (
            ("src", ""), ("srcset", ""), ("width", 0), ("height", 0), ("alt", {}))}
        path = urlsplit(value["src"]).path[len(media_url):]
        if not Asset.objects.using(alias).filter(legacy_key=path).exists():
            import_image(path, value, "4:5")


def reverse_media(apps, schema_editor):
    alias = schema_editor.connection.alias
    Asset = apps.get_model("cms", "MediaAsset")
    # New stable references cannot be dropped without breaking history/restoration.
    if Asset.objects.using(alias).exclude(version=0).exists():
        raise IrreversibleError("Hay fotos nuevas en la biblioteca. Exporta y adapta sus referencias antes de revertir.")
    def has_reference(value):
        if isinstance(value, dict):
            return "asset" in value or any(has_reference(v) for v in value.values())
        return isinstance(value, list) and any(has_reference(v) for v in value)
    for name in ("HomePublication", "PageRevision", "DraftRevision"):
        for row in apps.get_model("cms", name).objects.using(alias).all().iterator():
            if has_reference(row.snapshot) or has_reference(getattr(row, "draft_snapshot", {})):
                raise IrreversibleError("El historial contiene fotos de biblioteca; conserva este esquema.")
    for name in ("HomeSection", "HeroSlide", "PersonalizationService"):
        Model = apps.get_model("cms", name)
        for row in Model.objects.using(alias).all().iterator():
            fields = ["image_reference"]
            row.image_reference = {}
            if name == "HomeSection":
                props = deepcopy(row.props)
                for key in ("image", "mobile_image"):
                    ref = props.get(key)
                    if isinstance(ref, dict) and "asset" in ref:
                        asset = Asset.objects.using(alias).get(pk=ref["asset"])
                        props[key] = asset.versions[str(ref["version"])][ref["crop"]]
                row.props = props
                fields.append("props")
            row.save(update_fields=fields)
    # Deliberately retain imported rows/files; schema reverse may drop rows safely.


class Migration(migrations.Migration):
    dependencies = [("cms", "0019_heroslide_image_reference_and_more")]
    operations = [migrations.RunPython(migrate_media, reverse_media)]
