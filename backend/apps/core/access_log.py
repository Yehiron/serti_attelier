"""Redact capability URLs before Gunicorn interpolates access atoms."""

from typing import TYPE_CHECKING

from gunicorn.glogging import Logger

from .observability import normalize_order_path

if TYPE_CHECKING:

    class _LoggerBase:
        def atoms(self, resp, req, environ, request_time): ...
else:
    _LoggerBase = Logger


class PrivateOrderLogger(_LoggerBase):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        atoms["U"] = normalize_order_path(atoms["U"])
        return atoms
