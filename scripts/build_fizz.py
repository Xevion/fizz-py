#!/usr/bin/env python3
"""Build (or reuse) a liboqs-enabled Fizz for local development.

The post-quantum handshake needs a Fizz compiled against liboqs; the Homebrew
bottle ships FIZZ_HAVE_OQS=0. This builds Fizz from source against Homebrew's
liboqs/libsodium once, installing into a gitignored prefix that `just build`
then points `find_package(fizz)` at. Re-runs are a no-op unless --force.

This is the fast local loop. The deterministic, distribution-oriented build is
scripts/build_fizz_deps.py (getdeps, static-PIC, inside manylinux). See BUILDING.md.

Usage:
    python scripts/build_fizz.py ensure [--force]   # build if the prefix is stale
    python scripts/build_fizz.py prefix-path        # print CMAKE_PREFIX_PATH for cmake
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Fizz and Folly are versioned together; this tag must match the Homebrew Folly
# bottle's ABI (check `brew info folly`).
FIZZ_TAG = "v2026.06.08.00"
FIZZ_REPO = "https://github.com/facebookincubator/fizz"

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / ".dev" / "fizz-src"
BUILD = REPO / ".dev" / "fizz-build"
PREFIX = REPO / ".dev" / "fizz-prefix"


def brew_prefix() -> Path:
    """Locate the Homebrew prefix that supplies liboqs/libsodium/folly."""
    env = os.environ.get("HOMEBREW_PREFIX")
    if env:
        return Path(env)
    found = shutil.which("brew")
    if found:
        out = subprocess.run(
            [found, "--prefix"], capture_output=True, text=True, check=True
        )
        return Path(out.stdout.strip())
    default = Path("/home/linuxbrew/.linuxbrew")
    if default.exists():
        return default
    sys.exit(
        "Homebrew not found; set HOMEBREW_PREFIX or install brew (see BUILDING.md)."
    )


def prefix_path() -> str:
    """CMAKE_PREFIX_PATH so find_package(fizz) resolves to the OQS build first."""
    brew = brew_prefix()
    parts = [PREFIX, brew / "opt" / "liboqs", brew / "opt" / "libsodium", brew]
    return ";".join(str(p) for p in parts)


def is_built() -> bool:
    return (PREFIX / "lib" / "cmake" / "fizz" / "fizz-config.cmake").exists()


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def ensure(force: bool) -> None:
    if is_built() and not force:
        print(f"OQS Fizz already built at {PREFIX} (use --force to rebuild).")
        return

    if not (SRC / "fizz" / "CMakeLists.txt").exists():
        run(["git", "clone", "--depth", "1", "--branch", FIZZ_TAG, FIZZ_REPO, str(SRC)])

    if force and BUILD.exists():
        shutil.rmtree(BUILD)

    brew = brew_prefix()
    # BUILD_EXAMPLES=OFF is required: the bundled FizzTool fails -Werror under
    # OpenSSL 3.6 (deprecated EVP_PKEY_cmp); the library itself is fine.
    # find_package(liboqs CONFIG) inside Fizz auto-sets FIZZ_HAVE_OQS and links
    # OQS::oqs, so post-quantum support follows from liboqs being on the path.
    run(
        [
            "cmake",
            "-S",
            str(SRC / "fizz"),
            "-B",
            str(BUILD),
            "-G",
            "Ninja",
            f"-DCMAKE_INSTALL_PREFIX={PREFIX}",
            f"-DCMAKE_MODULE_PATH={SRC / 'build' / 'fbcode_builder' / 'CMake'}",
            f"-DCMAKE_PREFIX_PATH={brew};{brew / 'opt' / 'liboqs'};{brew / 'opt' / 'libsodium'}",
            "-DBUILD_EXAMPLES=OFF",
            "-DBUILD_TESTS=OFF",
        ]
    )
    run(["cmake", "--build", str(BUILD), "--target", "install"])
    print(f"\nOQS Fizz installed to {PREFIX}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ensure = sub.add_parser("ensure", help="build the OQS Fizz prefix if missing")
    p_ensure.add_argument(
        "--force", action="store_true", help="rebuild even if present"
    )
    sub.add_parser("prefix-path", help="print CMAKE_PREFIX_PATH for the OQS Fizz")
    args = parser.parse_args()

    if args.cmd == "ensure":
        ensure(args.force)
    elif args.cmd == "prefix-path":
        print(prefix_path())


if __name__ == "__main__":
    main()
