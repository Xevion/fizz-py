#!/usr/bin/env python3
"""cibuildwheel `before-all` for macOS and Windows.

The Linux path bakes the folly + fizz + liboqs tree into a manylinux image; there
is no such image for macOS/Windows, so the deps are built on the runner here. The
getdeps scratch dir is restored from actions/cache between runs (keyed by this
file's hash), so a warm cache makes getdeps a near-instant no-op rather than a
~40-minute rebuild.

Outputs (read by CMakeLists.txt at configure time, same as the Linux path):
    $FIZZPY_BUILD_INFO/prefix.txt      semicolon-joined CMAKE_PREFIX_PATH
    $FIZZPY_BUILD_INFO/module_dir.txt  dir holding fizz's bundled find-modules

Env (set by the workflow so the cache and CMake agree on locations):
    FIZZ_TAG, FIZZ_SRC, GETDEPS_SCRATCH, FIZZPY_BUILD_INFO
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Pin fizz to a release whose getdeps manifests pin a matching folly. liboqs is
# pinned by fizz's own manifest, so post-quantum support travels with the tag.
FIZZ_TAG = os.environ.get("FIZZ_TAG", "v2026.06.08.00")
FIZZ_SRC = Path(os.environ["FIZZ_SRC"])
SCRATCH = os.environ["GETDEPS_SCRATCH"]
OUT = Path(os.environ["FIZZPY_BUILD_INFO"])


def cmake_defines() -> str:
    # Static-PIC so _core links the tree in wholesale into one self-contained
    # module, matching the Linux build. PIC is a no-op on Windows but harmless.
    defines = {"CMAKE_POSITION_INDEPENDENT_CODE": "ON"}
    if platform.system() == "Darwin":
        # folly's C++17 (aligned operator new, std::uncaught_exceptions) needs
        # >= 10.13; without this getdeps defaults to 10.9 and folly fails to
        # compile. Match the wheel's MACOSX_DEPLOYMENT_TARGET so ABI agrees.
        defines["CMAKE_OSX_DEPLOYMENT_TARGET"] = os.environ.get(
            "MACOSX_DEPLOYMENT_TARGET", "11.0"
        )
    return json.dumps(defines)


def run(cmd: list[str], **kwargs: object) -> None:
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True, **kwargs)  # type: ignore[arg-type]


def main() -> None:
    getdeps = str(FIZZ_SRC / "build" / "fbcode_builder" / "getdeps.py")
    common = [
        "--extra-cmake-defines",
        cmake_defines(),
        f"--src-dir={FIZZ_SRC}",
        "--allow-system-packages",
    ]
    # getdeps only autodetects Visual Studio 2022; newer VS on the runner needs an
    # explicit pointer to vcvarsall.bat (located via vswhere in the workflow).
    vcvars = os.environ.get("VCVARS_PATH")
    if vcvars:
        common += ["--vcvars-path", vcvars]

    # A cache restore brings back the clone; only fetch when it's genuinely absent.
    if not (FIZZ_SRC / ".git").exists():
        if FIZZ_SRC.exists():
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
            ]
        )

    # getdeps skips deps already present in the (cached) scratch, so this is cheap
    # on a warm cache and does the full build on a cold one.
    run(
        [
            sys.executable,
            getdeps,
            "--scratch-path",
            SCRATCH,
            "build",
            "fizz",
            *common,
            "--no-tests",
        ]
    )

    OUT.mkdir(parents=True, exist_ok=True)
    # show-inst-dir must use the SAME flags as build — the manifest hash depends
    # on them — or it points at a different (unbuilt) scratch dir.
    inst = subprocess.run(
        [
            sys.executable,
            getdeps,
            "--scratch-path",
            SCRATCH,
            "show-inst-dir",
            "--recursive",
            "fizz",
            *common,
        ],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    prefix = ";".join(line for line in inst.splitlines() if line.strip())
    (OUT / "prefix.txt").write_text(prefix + "\n")

    # fizz/folly use bundled find-modules (FindSodium, FindZstd, …) that live in
    # the fizz source tree rather than installed config packages.
    (OUT / "module_dir.txt").write_text(
        str(FIZZ_SRC / "build" / "fbcode_builder" / "CMake") + "\n"
    )

    print(f"fizz dependency tree ready; prefix written to {OUT / 'prefix.txt'}")


if __name__ == "__main__":
    main()
