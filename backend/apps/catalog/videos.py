"""Bounded, content-based video validation and shell-free transcoding commands."""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.utils.translation import gettext_lazy as _

MAX_BYTES = 150 * 1024 * 1024
INVALID = "Usa un video MP4, MOV o WebM."


def probe(path: str) -> dict[str, Any]:
    result = subprocess.run(  # noqa: S603 — fixed executable, separate arguments.
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],  # noqa: S607
        capture_output=True,
        timeout=30,
        check=True,
    )
    return dict(json.loads(result.stdout))


def video_metadata(data: dict[str, Any]) -> tuple[int, int, float]:
    try:
        container = set(data["format"]["format_name"].split(","))
        if not container.intersection({"mov", "mp4", "m4v", "webm", "matroska"}):
            raise ValueError
        stream = next(
            s
            for s in data["streams"]
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        )
        width, height = int(stream["width"]), int(stream["height"])
        duration = float(data["format"].get("duration", stream.get("duration")))
        if not math.isfinite(duration) or duration <= 0 or min(width, height) < 2:
            raise ValueError
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError, StopIteration) as exc:
        raise ValidationError(_(INVALID)) from exc
    if duration > 60:
        raise ValidationError(_("El video no puede durar más de 60 segundos."))
    if width > 4096 or height > 4096:
        raise ValidationError(_("El video no puede superar 4096 x 4096 píxeles."))
    return width, height, duration


def validate_video(upload: File[bytes]) -> tuple[int, int, float]:
    if upload.size > MAX_BYTES:
        raise ValidationError(_("El video no puede superar 150 MB."))
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            upload.seek(0)
            total = 0
            with path.open("wb") as target:
                for chunk in upload.chunks():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValidationError(_("El video no puede superar 150 MB."))
                    target.write(chunk)
            return video_metadata(probe(str(path)))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValidationError(_(INVALID)) from exc
    finally:
        upload.seek(0)


def transcode_command(source: str, target: str) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        source,
        "-map",
        "0:V:0",
        "-vf",
        "scale=w='trunc(iw*min(1,min(1280/iw,1280/ih))/2)*2':"
        "h='trunc(ih*min(1,min(1280/iw,1280/ih))/2)*2',"
        "fps=fps='min(source_fps,30)':round=down,setsar=1",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        "-map_metadata",
        "-1",
        target,
    ]


def poster_command(source: str, target: str, duration: float) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-ss",
        "1" if duration > 1 else "0",
        "-i",
        source,
        "-frames:v",
        "1",
        "-update",
        "1",
        target,
    ]
