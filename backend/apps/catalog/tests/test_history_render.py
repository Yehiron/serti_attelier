import pytest


@pytest.mark.parametrize("diff", [{}, {"slug": ["a", "b"]}, {"care": [None, ""]}])
def test_guardado_sin_diff_legible_no_se_describe(diff):
    from types import SimpleNamespace

    from apps.catalog.audit_history import describe_event

    assert describe_event(SimpleNamespace(action="catalog.piece_updated", diff=diff)) == []


@pytest.mark.parametrize("action", ["created", "deleted", "published", "duplicated"])
def test_eventos_significativos_sin_diff_se_muestran(action):
    from types import SimpleNamespace

    from apps.catalog.audit_history import describe_event

    assert describe_event(SimpleNamespace(action=f"catalog.piece_{action}", diff={}))
