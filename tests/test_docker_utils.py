"""Tests for pipeline.common.docker_utils.

The integration cases require a running docker daemon. When it is not
available the whole group skips rather than failing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.common.docker_utils import (
    DockerUnavailableError,
    _safe_image_stub,
    assert_daemon_running,
    build_image,
    image_tag,
    run_container,
)


def _daemon_available() -> bool:
    try:
        assert_daemon_running()
        return True
    except DockerUnavailableError:
        return False


def _build_capable() -> tuple[bool, str]:
    """Probe whether we can actually build an image end-to-end.

    Environments with broken credential helpers or unreachable registries
    fail here even though the daemon itself pings fine; when that
    happens we skip the integration tests rather than mark them as
    failures unrelated to RepoEval's code.
    """
    if not _daemon_available():
        return False, "docker daemon not available"
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ctx = Path(tmp)
        df = ctx / "Dockerfile"
        df.write_text("FROM alpine:3.19\nCMD [\"true\"]\n")
        try:
            build_image(df, ctx, image_tag(df, "probe"))
        except Exception as e:  # noqa: BLE001
            return False, f"build probe failed: {e}"
    return True, ""


_BUILD_OK, _BUILD_REASON = _build_capable()

daemon_required = pytest.mark.skipif(
    not _BUILD_OK,
    reason=_BUILD_REASON or "docker build not available",
)


def test_image_tag_is_deterministic(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM alpine:3.19\nCMD echo hi\n")
    assert image_tag(df, "alpine") == image_tag(df, "alpine")


def test_image_tag_changes_with_dockerfile_content(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM alpine:3.19\n")
    a = image_tag(df, "alpine")
    df.write_text("FROM alpine:3.20\n")
    b = image_tag(df, "alpine")
    assert a != b


def test_image_tag_format(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM alpine\n")
    tag = image_tag(df, "hygiene")
    assert tag.startswith("repoeval-hygiene-")
    suffix = tag.split("-")[-1]
    assert len(suffix) == 12
    int(suffix, 16)


def test_image_tag_sanitises_hint(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM alpine\n")
    tag = image_tag(df, "HY GIE!NE/x")
    assert tag.startswith("repoeval-hygienex-")
    assert " " not in tag
    assert "!" not in tag
    assert "/" not in tag


def test_image_tag_empty_hint_falls_back(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM alpine\n")
    assert image_tag(df, "!!!").startswith("repoeval-img-")


def test_safe_image_stub_various():
    assert _safe_image_stub("alpine:3.19") == "alpine"
    assert _safe_image_stub("ghcr.io/org/tool:1.0") == "tool"
    assert _safe_image_stub("python:3.11-slim") == "python"
    assert _safe_image_stub("") == "img"


def test_build_refuses_dockerfile_outside_context(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    outside = tmp_path / "Dockerfile"
    outside.write_text("FROM alpine\n")
    with pytest.raises(ValueError, match="inside"):
        build_image(outside, ctx, "repoeval-bad-000000000000")


@daemon_required
def test_assert_daemon_running_succeeds():
    assert_daemon_running()


@daemon_required
def test_build_and_run_alpine_echo(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    df = ctx / "Dockerfile"
    df.write_text("FROM alpine:3.19\nCMD [\"echo\", \"hi\"]\n")

    tag = image_tag(df, "smoke")
    build_image(df, ctx, tag)

    result = run_container(tag, ["echo", "hi"])
    assert result.exit_code == 0
    assert "hi" in result.stdout
    assert result.timed_out is False
    assert result.image == tag


@daemon_required
def test_build_is_cache_hit_on_second_call(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    df = ctx / "Dockerfile"
    df.write_text("FROM alpine:3.19\nCMD [\"true\"]\n")
    tag = image_tag(df, "cache")

    first = build_image(df, ctx, tag)
    second = build_image(df, ctx, tag)
    assert first == second


@daemon_required
def test_run_container_captures_stderr(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    df = ctx / "Dockerfile"
    df.write_text("FROM alpine:3.19\n")
    tag = image_tag(df, "stderr")
    build_image(df, ctx, tag)

    result = run_container(tag, ["sh", "-c", "echo out; echo err >&2; exit 3"])
    assert result.exit_code == 3
    assert "out" in result.stdout
    assert "err" in result.stderr


@daemon_required
def test_run_container_with_mount(tmp_path: Path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    df = ctx / "Dockerfile"
    df.write_text("FROM alpine:3.19\n")
    tag = image_tag(df, "mount")
    build_image(df, ctx, tag)

    mount_source = tmp_path / "data"
    mount_source.mkdir()
    (mount_source / "greeting.txt").write_text("hello from host")

    result = run_container(
        tag,
        ["cat", "/mnt/greeting.txt"],
        mounts={mount_source: "/mnt"},
    )
    assert result.exit_code == 0
    assert "hello from host" in result.stdout
