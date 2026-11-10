"""Explicit current-version inputs for pre-concurrency regression scenarios."""

import re
from urllib.parse import parse_qs, urlsplit

from apps.cms.documents import document_key, get_document
from apps.cms.models import Page


def cms_version(obj=None):
    return get_document(document_key(obj)).draft_version


def cms_form_data(url, data):
    path = urlsplit(str(url))
    if not any(part in path.path for part in ("/cms/", "/editor/", "/publicaciones/")):
        return data
    match = re.search(r"/cms/page/(\d+)/", path.path)
    document = parse_qs(path.query).get("document", [""])[0]
    page = (
        Page.objects.get(pk=match[1])
        if match
        else (Page.objects.get(pk=document) if document.isdecimal() else None)
    )
    return {"expected_version": cms_version(page), **data}


def historical_public_bytes(apps, url, locale):
    """Exercise the real public view against the schema under migration.

    Selectors use historical models in that window. New additive options absent
    from the old schema read as defaults; no publication or stored byte changes.
    """
    from contextlib import ExitStack
    from unittest.mock import patch

    from django.test import Client

    home = apps.get_model("cms", "HomePublication")
    with ExitStack() as stack:
        stack.enter_context(patch("apps.cms.selectors.HomePublication", home))
        stack.enter_context(patch("apps.cms.selectors.Page", apps.get_model("cms", "Page")))
        if not any(field.name == "seo" for field in home._meta.concrete_fields):
            stack.enter_context(patch.object(home, "seo", {}, create=True))
        response = Client().get(url, {"locale": locale})
        assert response.status_code == 200
        return response.content
