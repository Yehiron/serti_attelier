from django.utils.translation import override
from unfold.widgets import UnfoldAdminSplitDateTimeWidget


def test_split_datetime_placeholders_are_spanish():
    with override("es"):
        html = UnfoldAdminSplitDateTimeWidget().render("valid_from", None)
    assert 'placeholder="Fecha"' in html
    assert 'placeholder="Hora"' in html
