from typing import Any

from rest_framework import serializers


class ProblemSerializer(serializers.Serializer[Any]):
    type = serializers.URLField()
    title = serializers.CharField()
    status = serializers.IntegerField()
    code = serializers.CharField()
    detail = serializers.CharField()


def public_responses(success: Any, *, not_found: bool = False) -> dict[Any, Any]:
    responses = {
        200: success,
        (400, "application/problem+json"): ProblemSerializer,
        (429, "application/problem+json"): ProblemSerializer,
    }
    if not_found:
        responses[(404, "application/problem+json")] = ProblemSerializer
    return responses
