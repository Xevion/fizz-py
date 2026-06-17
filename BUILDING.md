# Building fizzpy

The `_core` extension links Facebook's Fizz (C++ TLS 1.3). The post-quantum
handshake additionally requires a Fizz built against
[liboqs](https://github.com/open-quantum-safe/liboqs) — the Homebrew bottle and
vcpkg port both ship `FIZZ_HAVE_OQS=0`, so they negotiate classical groups only.

There are three build paths, for three different purposes:

| | Container dev (`just dev-build`) | Homebrew dev (`just build`) | CI wheels (`scripts/build_fizz_deps.py`) |
| --- | --- | --- | --- |
| Fizz/liboqs source | getdeps tree in `.dev/getdeps` | Homebrew + from-source Fizz | getdeps, all from source |
| Linkage | static, against the CI tree | static Fizz, shared liboqs via rpath | fully static-PIC, self-contained `.so` |
| Where | `manylinux_2_28` container | your machine | `manylinux_2_28` container |
| Optimized for | "builds here == builds in CI" | fastest iteration | deterministic, portable distribution |

## Container development (`just dev-*`) — recommended

The Homebrew loop links `_core` against Homebrew's *shared* folly, so a Homebrew
folly bump (now compiled for a newer glibc than many hosts) silently breaks every
local build. The container loop sidesteps that: it builds and runs `_core` inside
the same `manylinux_2_28` image the wheels use, against the prebuilt static
folly + Fizz + liboqs tree in `.dev/getdeps`. "Builds locally" and "builds in CI"
become the same statement.

```sh
just dev-up         # create/start the container + one-time system + pip setup
just dev-build      # editable-build _core against the getdeps tree (~10s inner loop)
just dev-test       # offline suite; `just dev-test "-- -m network"` runs live-network tests
just dev-shell      # interactive bash inside the container
just dev-down       # stop + remove the container
```

The trick that needs no path rewriting: the getdeps tree bakes absolute
`/project/...` paths into its CMake configs (it was built at `/project`), so the
repo is bind-mounted at `/project` inside the container and every baked path
resolves. A persistent container plus `docker exec` keeps the inner loop fast
(no per-change `docker run`/image build).

This requires the `.dev/getdeps` tree on disk (gitignored). Rebuild it inside the
image with `scripts/build_fizz_deps.py` if it's missing (~40 min, one-time). The
orchestration lives in `scripts/dev.py`.

## Homebrew development (`just build`) — fastest, host-dependent

Fast iteration when your host glibc is new enough for the current Homebrew folly
bottle. If `import fizzpy` fails with a `GLIBC_2.xx not found` error, your host is
too old — use the container loop above.

```sh
brew install fizz liboqs    # fizz pulls folly, boost, glog, gflags, libsodium, double-conversion
pip install -e .[dev] --no-build-isolation   # or: pip install scikit-build-core pybind11 pybind11-stubgen ruff pytest

just build      # build OQS Fizz if needed (cached), then editable-install _core
just test       # offline test suite; `just test ""` includes live network tests
just check      # ruff lint
just fmt        # ruff format + clang-format _core.cpp
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

`scripts/build_fizz_deps.py` is cibuildwheel's `before-all`. It builds the whole
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
