"""Optional selection with a safe no-JavaScript fallback."""

from typing import TYPE_CHECKING

from unfold.views import ChangeList

if TYPE_CHECKING:

    class _ChangeListBase:
        queryset: object

        def __init__(self, *args, **kwargs): ...
        def get_filters_params(self, params=None): ...
else:
    _ChangeListBase = ChangeList


class SelectionChangeList(_ChangeListBase):
    def get_filters_params(self, params=None):
        result = super().get_filters_params(params)
        result.pop("select", None)
        return result


class OptionalSelectionMixin:
    def get_changelist(self, request, **kwargs):
        return SelectionChangeList
