"""Optional selection with a safe no-JavaScript fallback."""

from unfold.views import ChangeList


class SelectionChangeList(ChangeList):
    def get_filters_params(self, params=None):
        result = super().get_filters_params(params)
        result.pop("select", None)
        return result


class OptionalSelectionMixin:
    def get_changelist(self, request, **kwargs):
        return SelectionChangeList
