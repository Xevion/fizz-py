#!/usr/bin/env python3
"""cibuildwheel `before-all`: build the folly + fizz + liboqs tree once per
manylinux container as static-PIC archives that the _core extension links in
wholesale, producing a single self-contained .so. liboqs is a fizz dependency in
fizz's own getdeps manifest, so the resulting fizz has FIZZ_HAVE_OQS=1 — real
post-quantum support.

Outputs (read by the per-wheel build via the CIBW environment):
    $FIZZPY_BUILD_INFO/prefix.txt      semicolon-joined CMAKE_PREFIX_PATH
    $FIZZPY_BUILD_INFO/module_dir.txt  dir holding fizz's bundled find-modules

The fast local equivalent is scripts/build_fizz.py (Homebrew, from-source). See
BUILDING.md.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Pin fizz to a release whose getdeps manifests pin a matching folly. liboqs is
# pinned by fizz's own manifest, so post-quantum support travels with the tag.
FIZZ_TAG = os.environ.get("FIZZ_TAG", "v2026.06.08.00")
FIZZ_SRC = Path(os.environ.get("FIZZ_SRC", "/opt/fizz-src"))
SCRATCH = os.environ.get("GETDEPS_SCRATCH", "/opt/fizz-deps")
OUT = Path(os.environ.get("FIZZPY_BUILD_INFO", "/opt/fizzpy-build"))

# AlmaLinux 8's system GCC (~8.5) is too old for folly's C++20; manylinux_2_28
# ships gcc-toolset-14. Static-PIC everywhere: -fPIC covers the autotools deps
# (libsodium, xz, …), CMAKE_POSITION_INDEPENDENT_CODE the cmake ones (folly,
# fizz, glog, …). We deliberately avoid --shared-lib, which would bake folly into
# libfizz.so AND drag it into _core a second time via fizz's cmake interface, so
# folly's gflags globals register twice and abort at import.
PIC_DEFINE = '{"CMAKE_POSITION_INDEPENDENT_CODE": "ON"}'


def toolset_env() -> dict[str, str]:
    """Environment after sourcing gcc-toolset-14, with -fPIC added to *FLAGS."""
    raw = subprocess.run(
        ["bash", "-c", "source /opt/rh/gcc-toolset-14/enable && env -0"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    env = dict(item.split("=", 1) for item in raw.split("\0") if "=" in item)
    env["CFLAGS"] = f"-fPIC {env.get('CFLAGS', '')}".strip()
    env["CXXFLAGS"] = f"-fPIC {env.get('CXXFLAGS', '')}".strip()
    return env


def run(cmd: list[str], env: dict[str, str]) -> str:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(
        cmd, check=True, env=env, text=True, capture_output=False
    ).stdout


def main() -> None:
    env = toolset_env()
    getdeps = str(FIZZ_SRC / "build" / "fbcode_builder" / "getdeps.py")
    common = [
        "--extra-cmake-defines",
        PIC_DEFINE,
        f"--src-dir={FIZZ_SRC}",
        "--allow-system-packages",
    ]

    # getdeps bootstraps its own CMake (needs OpenSSL/zlib up front); folly's link
    # interface references system libaio by absolute path. Install all before build.
    run(
        [
            "yum",
            "install",
            "-y",
            "git",
            "openssl-devel",
            "zlib-devel",
            "libaio-devel",
            "libunwind-devel",
        ],
        env,
    )

    if FIZZ_SRC.exists():
        import shutil

        shutil.rmtree(FIZZ_SRC)
    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            FIZZ_TAG,
            "https://github.com/facebookincubator/fizz",
            str(FIZZ_SRC),
        ],
        env,
    )

    run(
        [
            "python3",
            getdeps,
            "--scratch-path",
            SCRATCH,
            "build",
            "fizz",
            *common,
            "--no-tests",
        ],
        env,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    # show-inst-dir must use the SAME flags as build — the manifest hash depends
    # on them — or it points at a different (unbuilt) scratch dir.
    inst = subprocess.run(
        [
            "python3",
            getdeps,
            "--scratch-path",
            SCRATCH,
            "show-inst-dir",
            "--recursive",
            "fizz",
            *common,
        ],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    ).stdout
    prefix = ";".join(line for line in inst.split("\n") if line.strip())
    (OUT / "prefix.txt").write_text(prefix + "\n")

    # fizz/folly use bundled find-modules (FindSodium, FindZstd, …) that live in
    # the fizz source tree rather than installed config packages.
    (OUT / "module_dir.txt").write_text(
        str(FIZZ_SRC / "build" / "fbcode_builder" / "CMake") + "\n"
    )

    print(f"fizz dependency tree built; prefix written to {OUT / 'prefix.txt'}")


if __name__ == "__main__":
    main()
