"""Redact capability URLs before Gunicorn interpolates access atoms."""

from gunicorn.glogging import Logger

from .observability import normalize_order_path


class PrivateOrderLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        atoms["U"] = normalize_order_path(atoms["U"])
        return atoms
