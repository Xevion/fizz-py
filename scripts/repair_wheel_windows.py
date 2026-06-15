#!/usr/bin/env python3
"""delvewheel front-end for cibuildwheel's Windows `repair-wheel-command`.

getdeps installs each dep under $GETDEPS_SCRATCH/installed/<name>/ with DLLs in
bin/ and import libs in lib/, under content-addressed (hashed) names. We glob those
dirs and hand them to `delvewheel repair --add-path` so it can find and vendor the
shared deps (glog/gflags/openssl/...) into the wheel.

Invoked as: python scripts/repair_wheel_windows.py {dest_dir} {wheel}
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
