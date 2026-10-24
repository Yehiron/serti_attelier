from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from ..formatting import place_name
from ..models import Department, Municipality
from .base import PublicView
from .serializers import public_responses


class DepartmentSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.SerializerMethodField()

    def get_name(self, obj: Department | Municipality) -> str:
        return place_name(obj.name)


class MunicipalitySerializer(DepartmentSerializer):
    kind = serializers.CharField()


class DepartmentView(PublicView):
    @extend_schema(responses=public_responses(DepartmentSerializer(many=True)))
    def get(self, request: Request) -> Response:
        return Response(DepartmentSerializer(Department.objects.all(), many=True).data)


class MunicipalityView(PublicView):
    @extend_schema(responses=public_responses(MunicipalitySerializer(many=True), not_found=True))
    def get(self, request: Request, code: str) -> Response:
        if not Department.objects.filter(pk=code).exists():
            raise NotFound()
        return Response(
            MunicipalitySerializer(Municipality.objects.filter(department_id=code), many=True).data
        )
