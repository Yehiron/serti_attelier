from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import override_settings

from apps.catalog.api.serializers import PieceDetailSerializer, PieceListSerializer
from apps.catalog.forms import PieceVideoForm
from apps.catalog.models import PieceVideo
from apps.catalog.services import save_piece_video
from apps.catalog.tasks import process_piece_video
from apps.catalog.videos import MAX_BYTES, poster_command, transcode_command, validate_video

pytestmark = pytest.mark.django_db


def metadata(**kwargs: Any) -> dict[str, Any]:
    return {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "2"},
        "streams": [{"codec_type": "video", "width": 320, "height": 240}],
        **kwargs,
    }


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (metadata(), None),
        (metadata(format={"format_name": "mp4", "duration": "61"}), "60 segundos"),
        (metadata(streams=[]), "Usa un video"),
        (metadata(format={"format_name": "avi", "duration": "2"}), "Usa un video"),
        (metadata(streams=[{"codec_type": "video", "width": 5000, "height": 240}]), "4096"),
        (metadata(format={"format_name": "mp4", "duration": "nan"}), "Usa un video"),
    ],
)
def test_validation(data: dict[str, Any], error: str | None) -> None:
    upload = ContentFile(b"fake video", name="untrusted.exe")
    with patch("apps.catalog.videos.subprocess.run") as run:
        run.return_value.stdout = json.dumps(data)
        if error:
            with pytest.raises(ValidationError, match=error):
                validate_video(upload)
        else:
            assert validate_video(upload) == (320, 240, 2)
        assert upload.tell() == 0
        args, kwargs = run.call_args
        assert args[0][:7] == [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
        ]
        assert kwargs["timeout"] == 30 and kwargs["check"]
        assert not kwargs.get("shell")


def test_size_and_form() -> None:
    upload = ContentFile(b"x", name="video.mp4")
    upload.size = MAX_BYTES + 1
    with patch("apps.catalog.videos.probe") as probe:
        with pytest.raises(ValidationError, match="150 MB"):
            validate_video(upload)
        probe.assert_not_called()
    form = PieceVideoForm()
    form.cleaned_data = {"original": upload}
    with pytest.raises(ValidationError, match="150 MB"):
        form.clean_original()


def test_commands() -> None:
    cmd = transcode_command("input", "output")
    assert cmd[cmd.index("-crf") + 1] == "26"
    assert cmd[cmd.index("-preset") + 1] == "slow"
    assert "-an" in cmd and "+faststart" in cmd and "yuv420p" in cmd
    scale = cmd[cmd.index("-vf") + 1]
    assert "1280/iw" in scale and "1280/ih" in scale and "/2)*2" in scale
    assert "min(1," in scale and "min(source_fps,30)" in scale
    assert poster_command("input", "poster", 0.5)[3] == "0"
    assert poster_command("input", "poster", 2)[3] == "1"


def test_failure_and_retry_source(make_piece: Any, tmp_path: Path) -> None:
    with override_settings(PRIVATE_MEDIA_ROOT=tmp_path / "private", MEDIA_ROOT=tmp_path / "public"):
        obj = PieceVideo(
            piece=make_piece(published=False),
            original=ContentFile(b"x", name="v.mov"),
            alt_es="Video",
        )
        with (
            patch("apps.catalog.videos.validate_video"),
            patch("apps.catalog.tasks.process_piece_video.delay") as delay,
        ):
            save_piece_video(obj)
            delay.assert_not_called()
        with patch("apps.catalog.videos.probe", side_effect=RuntimeError("secret")):
            process_piece_video(obj.pk)
        obj.refresh_from_db()
        assert obj.processing_status == "failed"
        assert obj.error == "No se pudo procesar el video."
        assert obj.original.storage.exists(str(obj.original.name))
        with pytest.raises(ValueError, match="no public URL"):
            _ = obj.original.url
        assert PieceDetailSerializer().get_video(obj.piece) is None


def test_cleanup(make_piece: Any, tmp_path: Path, django_capture_on_commit_callbacks: Any) -> None:
    with override_settings(PRIVATE_MEDIA_ROOT=tmp_path / "private", MEDIA_ROOT=tmp_path / "public"):
        obj = PieceVideo.objects.create(
            piece=make_piece(published=False),
            original=ContentFile(b"old", name="old"),
            alt_es="Video",
        )
        storage, old = obj.original.storage, obj.original.name
        with django_capture_on_commit_callbacks(execute=True):
            obj.original = ContentFile(b"new", name="new")
            obj.save()
            assert storage.exists(str(old))
        assert not storage.exists(str(old))
        name = obj.original.name
        with django_capture_on_commit_callbacks(execute=True):
            obj.delete()
            assert storage.exists(str(name))
        assert not storage.exists(str(name))


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg and ffprobe are required for the real transcode test; no local installs",
)
def test_real_transcode(
    make_piece: Any, tmp_path: Path, django_capture_on_commit_callbacks: Any, client: Any
) -> None:
    clip = tmp_path / "clip.mp4"
    subprocess.run(  # noqa: S603
        [  # noqa: S607 — local test fixture generator.
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=24",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        timeout=30,
        check=True,
        capture_output=True,
    )
    with override_settings(PRIVATE_MEDIA_ROOT=tmp_path / "private", MEDIA_ROOT=tmp_path / "public"):
        piece = make_piece()
        assert client.get(f"/api/v1/catalog/pieces/{piece.slug}").json()["video"] is None
        obj = PieceVideo(
            piece=piece,
            original=ContentFile(clip.read_bytes(), name="iphone.mov"),
            alt_es="Video de joya",
        )
        with django_capture_on_commit_callbacks(execute=True):
            save_piece_video(obj)
            private_name = obj.original.name
            assert obj.processing_status == "pending"
        obj.refresh_from_db()
        assert obj.processing_status == "ready", obj.error
        assert not obj.original and not obj.original.storage.exists(str(private_name))
        from apps.catalog.videos import probe

        output = probe(obj.mp4.path)
        assert len(output["streams"]) == 1
        stream = output["streams"][0]
        assert stream["codec_name"] == "h264"
        assert stream["pix_fmt"] == "yuv420p"
        assert stream["r_frame_rate"] == "24/1"
        assert (obj.width, obj.height) == (320, 240)
        assert 1.9 <= obj.duration_seconds <= 2.1
        data = client.get(f"/api/v1/catalog/pieces/{piece.slug}").json()["video"]
        assert set(data) == {"src", "type", "width", "height", "duration_seconds", "alt", "poster"}
        assert data["type"] == "video/mp4"
        assert set(data["poster"]) == {"src", "srcset", "width", "height", "alt"}
        assert data["poster"]["width"] == 320 and data["poster"]["height"] == 240
        assert "video" not in PieceListSerializer(piece).data
        paths = [obj.mp4.name, obj.poster.name, *obj.poster_renditions["webp"].values()]
        storage = obj.mp4.storage
        with django_capture_on_commit_callbacks(execute=True):
            obj.delete()
        assert all(not storage.exists(path) for path in paths)


def test_mocked_success_contract_and_replacement(
    make_piece: Any, tmp_path: Path, django_capture_on_commit_callbacks: Any, client: Any
) -> None:
    from apps.catalog.tests.conftest import image_file

    with override_settings(PRIVATE_MEDIA_ROOT=tmp_path / "private", MEDIA_ROOT=tmp_path / "public"):
        piece = make_piece()
        obj = PieceVideo(
            piece=piece,
            original=ContentFile(b"input", name="v.mov"),
            alt_es="Video",
            alt_en="Jewelry video",
        )
        with patch("apps.catalog.videos.validate_video"), django_capture_on_commit_callbacks():
            save_piece_video(obj)
        original_name = str(obj.original.name)

        def transcode(args: list[str], **kwargs: Any) -> None:
            assert kwargs["check"] and kwargs["timeout"] in (60, 600)
            assert not kwargs.get("shell")
            target = Path(args[-1])
            target.write_bytes(
                image_file("PNG", (320, 240)).read()
                if target.suffix == ".png"
                else b"encoded video"
            )

        with (
            patch("apps.catalog.videos.probe", return_value=metadata()),
            patch("subprocess.run", side_effect=transcode),
            django_capture_on_commit_callbacks(execute=True),
        ):
            process_piece_video(obj.pk)
        obj.refresh_from_db()
        assert obj.processing_status == "ready" and not obj.original
        assert not obj.original.storage.exists(original_name)
        data = client.get(f"/api/v1/catalog/pieces/{piece.slug}").json()["video"]
        assert data == {
            "src": obj.mp4.url,
            "type": "video/mp4",
            "width": 320,
            "height": 240,
            "duration_seconds": 2.0,
            "alt": "Video",
            "poster": {
                "src": obj.poster.url,
                "srcset": f"{obj.poster.storage.url(obj.poster_renditions['webp']['320'])} 320w",
                "width": 320,
                "height": 240,
                "alt": "Video",
            },
        }
        translated = client.get(f"/api/v1/catalog/pieces/{piece.slug_en}?locale=en").json()
        assert translated["video"]["alt"] == "Jewelry video"
        assert "video" not in PieceListSerializer(piece).data
        paths = [str(obj.mp4.name), str(obj.poster.name), *obj.poster_renditions["webp"].values()]
        obj.original = ContentFile(b"replacement", name="new.webm")
        with (
            patch("apps.catalog.videos.validate_video"),
            patch("apps.catalog.tasks.process_piece_video.delay"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            save_piece_video(obj)
        assert obj.processing_status == "pending"
        assert all(not obj.mp4.storage.exists(path) for path in paths)
        assert client.get(f"/api/v1/catalog/pieces/{piece.slug}").json()["video"] is None


def test_detail_join_only(make_piece: Any, django_assert_num_queries: Any) -> None:
    from apps.catalog.selectors import piece_detail, published_pieces

    piece = make_piece()
    joins = published_pieces().query.select_related
    assert isinstance(joins, dict) and "video" not in joins
    with django_assert_num_queries(5):
        selected = piece_detail(piece.slug, "es")
        assert PieceDetailSerializer().get_video(selected) is None


def test_probe_unavailable_and_timeout() -> None:
    for failure in (FileNotFoundError(), subprocess.TimeoutExpired("ffprobe", 30)):
        with (
            patch("apps.catalog.videos.subprocess.run", side_effect=failure),
            pytest.raises(ValidationError, match="Usa un video"),
        ):
            validate_video(ContentFile(b"x", name="v.mp4"))


def test_service_rejects_invalid_before_save(make_piece: Any) -> None:
    obj = PieceVideo(
        piece=make_piece(published=False),
        original=ContentFile(b"x", name="v.mp4"),
        alt_es="Video",
    )
    with (
        patch("apps.catalog.videos.probe", return_value=metadata(streams=[])),
        pytest.raises(ValidationError, match="Usa un video"),
    ):
        save_piece_video(obj)
    assert not PieceVideo.objects.exists()


def test_video_schema_contract() -> None:
    from drf_spectacular.generators import SchemaGenerator

    with override_settings(API_SCHEMA_PUBLIC=True):
        schema = SchemaGenerator().get_schema(request=None, public=True)  # type: ignore[no-untyped-call]
    assert schema is not None
    schemas = schema["components"]["schemas"]
    assert schemas["PieceDetail"]["properties"]["video"]["nullable"]
    assert "video" not in schemas["PieceList"]["properties"]
    assert set(schemas["Video"]["properties"]) == {
        "src",
        "type",
        "width",
        "height",
        "duration_seconds",
        "alt",
        "poster",
    }


def test_inline_permissions_follow_images() -> None:
    from django.contrib import admin
    from django.contrib.auth.models import Group
    from django.test import RequestFactory

    from apps.accounts.models import User
    from apps.accounts.roles import CONTENIDO, OPERACIONES, PROPIETARIO
    from apps.accounts.services import sync_roles
    from apps.catalog.admin import PieceImageInline, PieceVideoInline
    from apps.catalog.models import Piece

    sync_roles()
    for index, role in enumerate((PROPIETARIO, OPERACIONES, CONTENIDO, None)):
        user = User.objects.create_user(
            username=f"video-staff-{index}", email=f"video-{index}@example.com", is_staff=True
        )
        if role:
            user.groups.add(Group.objects.get(name=role))
        request = RequestFactory().get("/admin/")
        request.user = user
        image = PieceImageInline(Piece, admin.site)
        video = PieceVideoInline(Piece, admin.site)
        for action in ("add", "change", "delete", "view"):
            assert getattr(video, f"has_{action}_permission")(request, None) == getattr(
                image, f"has_{action}_permission"
            )(request, None)
        assert video.has_add_permission(request, None) == bool(role)
        assert video.has_delete_permission(request, None) == (role in (PROPIETARIO, OPERACIONES))


def test_partial_failure_cleanup_and_retry(
    make_piece: Any, tmp_path: Path, django_capture_on_commit_callbacks: Any
) -> None:
    from apps.catalog.tests.conftest import image_file

    with override_settings(PRIVATE_MEDIA_ROOT=tmp_path / "private", MEDIA_ROOT=tmp_path / "public"):
        obj = PieceVideo.objects.create(
            piece=make_piece(published=False),
            original=ContentFile(b"input", name="v.mov"),
            alt_es="Video",
        )
        private_name = str(obj.original.name)

        def encode(args: list[str], **kwargs: Any) -> None:
            Path(args[-1]).write_bytes(
                image_file("PNG", (320, 240)).read() if args[-1].endswith(".png") else b"video"
            )

        with (
            patch("apps.catalog.videos.probe", return_value=metadata()),
            patch("subprocess.run", side_effect=encode),
        ):
            with patch("apps.catalog.tasks.build_renditions", side_effect=OSError("secret")):
                process_piece_video(obj.pk)
            obj.refresh_from_db()
            assert obj.processing_status == "failed"
            assert obj.original.storage.exists(private_name)
            assert not list((tmp_path / "public").rglob("*.mp4"))
            assert not list((tmp_path / "public").rglob("*.webp"))
            with django_capture_on_commit_callbacks(execute=True):
                process_piece_video(obj.pk)
        obj.refresh_from_db()
        assert obj.processing_status == "ready"
        assert not obj.original.storage.exists(private_name)
        paths = [str(obj.mp4.name), str(obj.poster.name), *obj.poster_renditions["webp"].values()]
        with django_capture_on_commit_callbacks(execute=True):
            obj.piece.delete()
        assert all(not obj.mp4.storage.exists(path) for path in paths)
