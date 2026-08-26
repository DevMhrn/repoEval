"""
Docker helpers.

Thin wrapper around the ``docker`` SDK for the operations RepoEval
performs: verify the daemon is up, build an image with a deterministic
tag, and run a one-shot container that captures stdout/stderr.

Design
------
- :func:`image_tag` is content-addressed by the Dockerfile bytes so two
  identical Dockerfiles hash to the same tag. Rebuilds are skipped when
  the local image cache already has the tag.
- :func:`build_image` requires the Dockerfile to live inside the build
  context directory; passing a Dockerfile from outside is refused.
- :func:`run_container` always uses ``--rm`` semantics and generates a
  unique container name per invocation so parallel runs never collide.
- If the ``docker`` SDK is not installed, every entry point raises
  :class:`DockerUnavailableError` early with a clear reason.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

try:
    import docker
    from docker.errors import DockerException, ImageNotFound

    _HAS_SDK = True
except ImportError:  # pragma: no cover — exercised in envs without the SDK
    docker = None  # type: ignore[assignment]
    DockerException = Exception  # type: ignore[assignment,misc]
    ImageNotFound = Exception  # type: ignore[assignment,misc]
    _HAS_SDK = False


class DockerUnavailableError(Exception):
    """Raised when the docker SDK or daemon is unavailable."""


class DockerBuildError(Exception):
    """Raised when an image build fails."""


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool = False
    image: str = ""
    container_name: str = ""


def _client() -> Any:
    if not _HAS_SDK:
        raise DockerUnavailableError("docker SDK not installed")
    return docker.from_env()


def assert_daemon_running() -> None:
    """Ping the daemon; raise :class:`DockerUnavailableError` on failure."""
    try:
        _client().ping()
    except DockerUnavailableError:
        raise
    except Exception as e:  # noqa: BLE001 — surface any daemon problem uniformly
        raise DockerUnavailableError(f"docker daemon unreachable: {e}") from e


def image_tag(dockerfile_path: Path, hint: str = "img") -> str:
    """Return ``repoeval-<hint>-<sha256(dockerfile)[:12]>``.

    If the Dockerfile bytes change, the tag changes; if the *base image*
    is updated upstream but the Dockerfile is unchanged, the tag stays
    the same and a rebuild is skipped. That's a deliberate caching
    trade-off — pinning the base by digest inside the Dockerfile is how
    callers opt out of it.
    """
    digest = hashlib.sha256(dockerfile_path.read_bytes()).hexdigest()[:12]
    safe = "".join(c for c in hint if c.isalnum() or c in "-_").lower() or "img"
    return f"repoeval-{safe}-{digest}"


def build_image(
    dockerfile_path: Path,
    context_dir: Path,
    tag: str,
    *,
    log_stream: TextIO | Callable[[str], None] | None = None,
) -> str:
    """Build ``dockerfile_path`` inside ``context_dir`` and tag as ``tag``.

    If the local image cache already has an image tagged ``tag``, its ID
    is returned without rebuilding.
    """
    if not dockerfile_path.is_relative_to(context_dir):
        raise ValueError("dockerfile must live inside context_dir")

    client = _client()
    try:
        return client.images.get(tag).id
    except ImageNotFound:
        pass

    dockerfile_rel = dockerfile_path.relative_to(context_dir).as_posix()
    try:
        image, build_logs = client.images.build(
            path=str(context_dir),
            dockerfile=dockerfile_rel,
            tag=tag,
            rm=True,
            forcerm=True,
        )
    except DockerException as e:
        raise DockerBuildError(f"build failed for {tag}: {e}") from e

    if log_stream is not None:
        for chunk in build_logs:
            if isinstance(chunk, dict) and "stream" in chunk:
                _write(log_stream, chunk["stream"])

    return image.id


def run_container(
    image: str,
    cmd: list[str] | str,
    *,
    mounts: dict[Path, str] | None = None,
    env: dict[str, str] | None = None,
    timeout_sec: int = 600,
    working_dir: str | None = None,
) -> RunResult:
    """Run a container and capture output. Always cleaned up on exit."""
    client = _client()

    name = f"{_safe_image_stub(image)}-run-{secrets.token_hex(2)}"

    volumes: dict[str, dict[str, str]] = {}
    if mounts:
        for host_path, container_path in mounts.items():
            volumes[str(host_path)] = {"bind": container_path, "mode": "rw"}

    start = time.monotonic()
    container = client.containers.run(
        image=image,
        command=cmd,
        name=name,
        detach=True,
        environment=env or {},
        volumes=volumes,
        working_dir=working_dir,
    )

    timed_out = False
    exit_code = -1
    try:
        try:
            result = container.wait(timeout=timeout_sec)
            exit_code = result.get("StatusCode", -1)
        except Exception:  # noqa: BLE001 — treat any wait failure as timeout
            timed_out = True
            try:
                container.kill()
            except Exception:  # noqa: BLE001
                pass

        duration = time.monotonic() - start
        stdout = container.logs(stdout=True, stderr=False).decode(
            "utf-8", errors="replace"
        )
        stderr = container.logs(stdout=False, stderr=True).decode(
            "utf-8", errors="replace"
        )
    finally:
        try:
            container.remove(force=True)
        except Exception:  # noqa: BLE001
            pass

    return RunResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_sec=duration,
        timed_out=timed_out,
        image=image,
        container_name=name,
    )


def _write(sink: TextIO | Callable[[str], None], text: str) -> None:
    if callable(sink):
        sink(text)
    else:
        sink.write(text)


def _safe_image_stub(image: str) -> str:
    stub = image.split(":", 1)[0].rsplit("/", 1)[-1]
    return "".join(c for c in stub if c.isalnum() or c in "-_") or "img"
