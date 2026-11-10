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
