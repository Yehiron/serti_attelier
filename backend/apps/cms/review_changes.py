"""Semantic editorial comparison shared by review, history and the pending count."""

from .registry import REGISTRY, editorial_props


def comparable(value):
    if isinstance(value, str):
        # Browser textareas submit CRLF; the stored text may use LF. Same content, no change.
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        if "asset" in value and value.get("version") == 0:
            from .models import MediaAsset

            asset = MediaAsset.objects.get(pk=value["asset"])
            return comparable(asset.versions["0"][value["crop"]])
        value = {
            k: v
            for k, v in value.items()
            if k != "image_reference" or (v and v.get("version") != 0)
        }
        return {
            key: normalized
            for key, item in value.items()
            if (normalized := comparable(item)) is not None
        }
    if isinstance(value, list):
        return [comparable(item) for item in value]
    return value


def equivalent(left, right):
    return comparable(left) == comparable(right)


def display(value):
    if value is None or value == "":
        return "Sin contenido"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    return str(value)


def home_groups(current, previous):
    before = {row["id"]: comparable(row) for row in previous}
    after = {row["id"]: comparable(row) for row in current}
    groups = []
    for key in dict.fromkeys((*after, *before)):
        row, old = after.get(key), before.get(key)
        source = row or old
        spec = REGISTRY.get(source.get("kind"))
        group = {
            "name": spec.name if spec else "Sección",
            "icon": spec.icon if spec else "article",
            "rows": [],
        }

        def add(label, left, right, group=group):
            if not equivalent(left, right):
                group["rows"].append(
                    {"label": label, "before": display(left), "after": display(right)}
                )

        if row is None or old is None:
            add("Sección", "Presente" if old else None, "Presente" if row else None)
        else:
            add("Visibilidad", old.get("is_visible", True), row.get("is_visible", True))
            labels = {
                "title": "Título",
                "subtitle": "Subtítulo",
                "body": "Texto",
                "cta_label": "Texto del enlace",
                "image_alt": "Texto alternativo",
            }
            for field, label in labels.items():
                for lang, language in (("es", "español"), ("en", "inglés")):
                    add(
                        f"{label} · {language}",
                        old.get(f"{field}_{lang}"),
                        row.get(f"{field}_{lang}"),
                    )
            if spec:
                left = editorial_props(spec.kind, old.get("props", {}))
                right = editorial_props(spec.kind, row.get("props", {}))
                for label in dict.fromkeys((*left, *right)):
                    add(label, left.get(label), right.get(label))
            for field, label in (
                ("image", "Foto de respaldo"),
                ("image_reference", "Foto y recorte"),
                ("slides", "Fotos del carrusel"),
            ):
                if not equivalent(old.get(field), row.get(field)):
                    if field == "slides":

                        def photos(items):
                            return " · ".join(
                                f"{i + 1}. "
                                f"{'Celular' if s.get('device') == 'mobile' else 'Computador'}: "
                                f"{s.get('alt_es') or s.get('alt') or 'Foto'} / "
                                f"{s.get('alt_en') or ''}"
                                for i, s in enumerate(items or [])
                            )

                        add(label, photos(old.get(field)), photos(row.get(field)))
                        # Replacements with identical alt still need one visible change.
                        if not group["rows"] or group["rows"][-1]["label"] != label:
                            group["rows"].append(
                                {
                                    "label": label,
                                    "before": "Fotos anteriores",
                                    "after": "Fotos actualizadas",
                                }
                            )
                    else:
                        add(
                            label,
                            "Foto anterior" if old.get(field) else None,
                            "Foto actualizada" if row.get(field) else None,
                        )
            for field in sorted(set(old) | set(row)):
                if (
                    field.startswith("cta_") and not field.startswith("cta_label")
                ) or field == "collection_id":
                    add(
                        "Destino del enlace" if field != "collection_id" else "Colección",
                        old.get(field),
                        row.get(field),
                    )
        if group["rows"]:
            groups.append(group)
    common = before.keys() & after.keys()
    left, right = ([k for k in rows if k in common] for rows in (before, after))
    if left != right:
        groups.append(
            {
                "name": "Inicio",
                "icon": "reorder",
                "rows": [
                    {
                        "label": "Orden de las secciones",
                        "before": ", ".join(
                            REGISTRY[row.get("kind")].name
                            if row.get("kind") in REGISTRY
                            else "Sección"
                            for row in previous
                        ),
                        "after": ", ".join(
                            REGISTRY[row.get("kind")].name
                            if row.get("kind") in REGISTRY
                            else "Sección"
                            for row in current
                        ),
                    }
                ],
            }
        )
    return groups


def page_comparison(snapshot, kind):
    """Read old revisions using only the fields owned by this page type."""
    from copy import deepcopy

    result = deepcopy(snapshot or {})
    for lang in ("es", "en"):
        data = result.get(lang, {})
        source = data.get("source", data)
        if kind != "personalize":
            for field in ("process_title", "faq_title", "process", "faq"):
                data.pop(field, None)
                source.pop(field, None)
        else:
            for field, section in (("process_title", "process"), ("faq_title", "faq")):
                # Before these source fields existed, the headings lived in the sections.
                source.setdefault(field, data.get(section, {}).get("title", ""))
    if kind != "personalize":
        result.pop("_body_enabled", None)
    return result


def page_groups(current, previous, *, kind=None):
    if kind is not None:
        current = page_comparison(current, kind)
        previous = page_comparison(previous, kind)
    groups = []
    if bool(current.get("_body_enabled")) != bool((previous or {}).get("_body_enabled")):
        groups.append(
            {
                "name": "Contenido de Personaliza",
                "icon": "article",
                "rows": [
                    {
                        "label": "Mostrar el contenido antes de los pasos",
                        "before": display(bool((previous or {}).get("_body_enabled"))),
                        "after": display(bool(current.get("_body_enabled"))),
                    }
                ],
            }
        )
    labels = {
        "title": "Título",
        "body": "Contenido",
        "slug": "Dirección",
        "process": "Proceso de encargo",
        "faq": "Preguntas frecuentes",
        "question": "Pregunta",
        "answer": "Respuesta",
        "description": "Descripción",
        "process_title": "Título del proceso",
        "faq_title": "Título de preguntas frecuentes",
        "position": "Posición",
        "items": "Elemento",
        "steps": "Paso",
        "source": "",
    }
    group = {"name": "Contenido de la página", "icon": "article", "rows": []}

    def visit(left, right, path, language):
        if equivalent(left, right):
            return
        if isinstance(left, dict) or isinstance(right, dict):
            left = left if isinstance(left, dict) else {}
            right = right if isinstance(right, dict) else {}
            if "source" in left or "source" in right:
                # Original translations own the text; localized fallbacks must not duplicate it.
                visit(left.get("source", {}), right.get("source", {}), path, language)
                left = {k: v for k, v in left.items() if k in {"process", "faq"}}
                right = {k: v for k, v in right.items() if k in {"process", "faq"}}
            for key in dict.fromkeys((*left, *right)):
                if key == "title" and path in {"Proceso de encargo", "Preguntas frecuentes"}:
                    continue
                # Rendered HTML repeats the source text; show the editorial source once.
                if key in {"html", "body_html", "answer_html", "description_html"}:
                    continue
                visit(
                    left.get(key),
                    right.get(key),
                    " · ".join(filter(None, (path, labels.get(key, key)))),
                    language,
                )
        elif isinstance(left, list) or isinstance(right, list):
            left, right = left or [], right or []
            for i in range(max(len(left), len(right))):
                visit(
                    left[i] if i < len(left) else None,
                    right[i] if i < len(right) else None,
                    f"{path} {i + 1}",
                    language,
                )
        else:
            group["rows"].append(
                {"label": f"{path} · {language}", "before": display(left), "after": display(right)}
            )

    for locale, language in (("es", "español"), ("en", "inglés")):
        visit((previous or {}).get(locale, {}), current.get(locale, {}), "", language)
    if group["rows"]:
        groups.append(group)
    return groups


def change_lines(groups):
    return [
        f"{group['name']} · {row['label']}: {row['before']} → {row['after']}."
        for group in groups
        for row in group["rows"]
    ]
