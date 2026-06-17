#!/usr/bin/env python3
"""Containerized local dev loop — isolated from host Homebrew/glibc drift.

The fast Homebrew loop (scripts/build_fizz.py) links _core against Homebrew's
*shared* folly, so a Homebrew folly bump (now compiled for a newer glibc than
this host) silently breaks every local build. This loop sidesteps that entirely:
it builds and runs _core inside the same manylinux_2_28 image the wheels use,
against the prebuilt static folly+fizz+liboqs tree in .dev/getdeps. "Builds
locally" and "builds in CI" become the same statement.

The trick that needs no path rewriting: the getdeps tree bakes absolute
/project/... paths into its CMake configs (it was built at /project), so the repo
is mounted at /project inside the container and every baked path resolves.

Usage:
    python scripts/dev.py up                 # create/start the container + one-time setup
    python scripts/dev.py build              # editable-build _core (the ~10s inner loop)
    python scripts/dev.py test [pytest args] # run the suite (defaults to the offline subset)
    python scripts/dev.py shell              # interactive bash inside the container
    python scripts/dev.py run -- cmd...      # arbitrary command with the build env set
    python scripts/dev.py down               # stop + remove the container

Requires the .dev/getdeps tree on disk (gitignored). Rebuild it with
scripts/build_fizz_deps.py inside the image if it's missing (~40 min, one-time).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONTAINER = "fizzpy-dev"
IMAGE = "quay.io/pypa/manylinux_2_28_x86_64:latest"
PYTHON = "/opt/python/cp310-cp310/bin/python"
GETDEPS = REPO / ".dev" / "getdeps"
SETUP_MARKER = "/opt/.fizzpy-dev-setup-done"

# System packages the static tree links against but doesn't vendor: OpenSSL 1.1
# dev symlinks (fizz's baked link line references /usr/lib64/libssl.so), libaio
# (folly async I/O) and libunwind (folly exception unwinding).
SYSTEM_PACKAGES = ["openssl-devel", "libaio-devel", "libunwind-devel"]
BUILD_DEPS = [
    "scikit-build-core",
    "pybind11",
    "pybind11-stubgen",
    "certifi",
    "pytest",
    "requests",
    "httpx",
]

# Container-side shell that derives the build/runtime paths from the getdeps tree
# (globbed at /project, so the baked /project/... paths match) and puts the
# target interpreter on PATH. Prepended to every action that touches the build.
PREAMBLE = r"""
set -e
export PATH="/opt/python/cp310-cp310/bin:$PATH"
export CMAKE_PREFIX_PATH="$(tr '\n' ';' < /project/.dev/getdeps-prefixes.txt)"
export FIZZ_CMAKE_MODULE_DIR="$(echo /project/.dev/getdeps/repos/*folly*/build/fbcode_builder/CMake)"
export LD_LIBRARY_PATH="$(echo /project/.dev/getdeps/installed/*/lib /project/.dev/getdeps/installed/*/lib64 | tr ' ' ':'):${LD_LIBRARY_PATH:-}"
"""


def _docker(
    *args: str, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], check=check, text=True, capture_output=capture
    )


def _container_state() -> str:
    """'running', 'stopped', or 'absent'."""
    out = _docker(
        "ps",
        "-a",
        "--filter",
        f"name=^{CONTAINER}$",
        "--format",
        "{{.State}}",
        capture=True,
        check=False,
    ).stdout.strip()
    if not out:
        return "absent"
    return "running" if out.startswith("running") else "stopped"


def _exec(script: str, *, interactive: bool = False) -> int:
    """Run a bash snippet inside the container (with the build env preamble)."""
    flags = ["-it"] if interactive else []
    proc = _docker(
        "exec", *flags, CONTAINER, "bash", "-c", PREAMBLE + script, check=False
    )
    return proc.returncode


def _require_tree() -> None:
    if not (GETDEPS / "installed" / "fizz").exists():
        sys.exit(
            f"getdeps tree missing at {GETDEPS}. Rebuild it inside the image with "
            "scripts/build_fizz_deps.py (~40 min, one-time). See BUILDING.md."
        )


def up() -> None:
    """Create/start the container and run one-time system + pip setup."""
    _require_tree()
    state = _container_state()
    if state == "absent":
        print(f"+ creating container {CONTAINER} from {IMAGE}", flush=True)
        _docker(
            "run",
            "-d",
            "--name",
            CONTAINER,
            "-v",
            f"{REPO}:/project",
            "-w",
            "/project",
            IMAGE,
            "sleep",
            "infinity",
        )
    elif state == "stopped":
        print(f"+ starting container {CONTAINER}", flush=True)
        _docker("start", CONTAINER)

    # One-time, marker-guarded: dnf + pip are slow; the build loop must not pay them.
    setup = (
        f"test -f {SETUP_MARKER} && exit 0\n"
        f"dnf install -y {' '.join(SYSTEM_PACKAGES)}\n"
        f"{PYTHON} -m pip install -q {' '.join(BUILD_DEPS)}\n"
        f"touch {SETUP_MARKER}\n"
    )
    print("+ ensuring system + pip deps (one-time)", flush=True)
    if _exec(setup) != 0:
        sys.exit("container setup failed")
    print(f"container {CONTAINER} ready")


def _ensure_up() -> None:
    if _container_state() != "running":
        up()


def build() -> None:
    """Editable-build _core against the getdeps tree (the fast inner loop)."""
    _ensure_up()
    script = (
        f"{PYTHON} -m pip install -e . --no-build-isolation "
        "-C build-dir=.dev/build-container "
        '-C cmake.define.CMAKE_PREFIX_PATH="$CMAKE_PREFIX_PATH" '
        '-C cmake.define.FIZZ_CMAKE_MODULE_DIR="$FIZZ_CMAKE_MODULE_DIR"'
    )
    sys.exit(_exec(script))


def test(args: list[str]) -> None:
    _ensure_up()
    # Default to the offline, deterministic subset (mirrors the Justfile default).
    pytest_args = " ".join(args) if args else "-m 'not network'"
    sys.exit(_exec(f"{PYTHON} -m pytest {pytest_args}"))


def shell() -> None:
    _ensure_up()
    sys.exit(_exec("exec bash", interactive=True))


def run(args: list[str]) -> None:
    _ensure_up()
    if not args:
        sys.exit("run: expected a command after --")
    sys.exit(_exec(" ".join(args)))


def down() -> None:
    if _container_state() != "absent":
        print(f"+ removing container {CONTAINER}", flush=True)
        _docker("rm", "-f", CONTAINER, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("up", help="create/start the container + one-time setup")
    sub.add_parser("build", help="editable-build _core (fast inner loop)")
    p_test = sub.add_parser("test", help="run the test suite")
    p_test.add_argument("args", nargs=argparse.REMAINDER, help="pytest args")
    sub.add_parser("shell", help="interactive bash in the container")
    p_run = sub.add_parser("run", help="run an arbitrary command with the build env")
    p_run.add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("down", help="stop + remove the container")
    args = parser.parse_args()

    if args.cmd == "up":
        up()
    elif args.cmd == "build":
        build()
    elif args.cmd == "test":
        # argparse.REMAINDER keeps a leading "--"; drop it.
        test([a for a in args.args if a != "--"])
    elif args.cmd == "shell":
        shell()
    elif args.cmd == "run":
        run([a for a in args.args if a != "--"])
    elif args.cmd == "down":
        down()


if __name__ == "__main__":
    main()
