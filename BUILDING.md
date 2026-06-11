# Building fizzpy

The `_core` extension links Facebook's Fizz (C++ TLS 1.3). The post-quantum
handshake additionally requires a Fizz built against
[liboqs](https://github.com/open-quantum-safe/liboqs) — the Homebrew bottle and
vcpkg port both ship `FIZZ_HAVE_OQS=0`, so they negotiate classical groups only.

There are two build paths, for two different purposes:

| | Local dev (`just build`) | CI wheels (`ci/build_fizz_deps.py`) |
| --- | --- | --- |
| Fizz/liboqs source | Homebrew + from-source Fizz | getdeps, all from source |
| Linkage | static Fizz, shared liboqs via rpath | fully static-PIC, self-contained `.so` |
| Where | your machine | `manylinux_2_28` container |
| Optimized for | fast iteration | deterministic, portable distribution |

## Local development (`just`)

```sh
brew install fizz liboqs    # fizz pulls folly, boost, glog, gflags, libsodium, double-conversion
git submodule update --init pybind11
pip install -e .[dev] --no-build-isolation   # or: pip install scikit-build-core pybind11 pybind11-stubgen ruff pytest

just build      # build OQS Fizz if needed (cached), then editable-install _core
just test       # offline test suite; `just test ""` includes live network tests
just check      # ruff lint
just fmt        # ruff format + clang-format main.cpp
```

`just build` runs `scripts/build_fizz.py ensure`, which compiles a liboqs-enabled
Fizz into the gitignored `.dev/fizz-prefix` once (subsequent runs are a no-op;
`python scripts/build_fizz.py ensure --force` rebuilds), then editable-installs
`_core` with `find_package(fizz)` pointed at that prefix.

- **C++20 is required** — current Folly (2026.06) dropped C++17.
- Fizz and Folly are versioned together. The tag in `scripts/build_fizz.py` must
  match the Homebrew Folly bottle, or the ABI won't match.
- `find_package(liboqs CONFIG)` inside Fizz auto-sets `FIZZ_HAVE_OQS` and links
  `OQS::oqs`. `BUILD_EXAMPLES=OFF` is required: the bundled FizzTool fails to
  compile under OpenSSL 3.6 (`-Werror` on the deprecated `EVP_PKEY_cmp`); the
  library itself is fine.

## Portable wheels (CI)

`ci/build_fizz_deps.py` is cibuildwheel's `before-all`. It builds the whole
folly + Fizz + liboqs tree once per `manylinux_2_28` container as static-PIC
archives, which `_core` links in wholesale — a single self-contained extension
with exactly one copy of folly. (Using getdeps `--shared-lib` instead would bake
folly into `libfizz.so` *and* drag it into `_core` again, double-registering
folly's gflags globals and aborting at import.) The build settings live in
`[tool.cibuildwheel]` in `pyproject.toml`.

## Verify

```sh
python -c "import fizzpy; print(fizzpy.get('https://www.cloudflare.com').tls)"
# group should be 'X25519MLKEM768', group_code 4588
```
