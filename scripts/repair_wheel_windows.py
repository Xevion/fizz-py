#!/usr/bin/env python3
"""cibuildwheel `repair-wheel-command` for Windows (delvewheel front-end).

The getdeps tree is built static-PIC, but glog/gflags still export as shared
libraries, so `_core.pyd` carries a runtime dependency on `glog.dll` (and its
transitive DLLs). delvewheel only searches `PATH` for DLLs to vendor, and the
getdeps install dirs aren't on it — so a bare `delvewheel repair` dies with
"Unable to find library: glog.dll". This is the Windows analogue of the
LD_LIBRARY_PATH / DYLD_LIBRARY_PATH injection the Linux/macOS repair commands do.

getdeps installs each dependency under $GETDEPS_SCRATCH/installed/<name>/, with
runtime DLLs in bin/ (CMake's RUNTIME destination) and import libs in lib/. We
point delvewheel at every such dir via --add-path so it can discover and bundle
the whole dependency chain into the wheel.

Invoked by cibuildwheel as:
    python scripts/repair_wheel_windows.py {dest_dir} {wheel}
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    dest_dir, wheel = sys.argv[1], sys.argv[2]
    scratch = Path(os.environ["GETDEPS_SCRATCH"])

    installed = scratch / "installed"
    dll_dirs = [
        d for name in ("bin", "lib") for d in installed.glob(f"*/{name}") if d.is_dir()
    ]
    add_path = os.pathsep.join(str(d) for d in dll_dirs)

    cmd = [
        sys.executable,
        "-m",
        "delvewheel",
        "repair",
        "--add-path",
        add_path,
        "-w",
        dest_dir,
        "-v",
        wheel,
    ]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
