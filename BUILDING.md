# Building fizzpy

There are no prebuilt wheels yet. The `_core` extension links Facebook's Fizz
(C++ TLS 1.3). The post-quantum handshake additionally requires a Fizz built
against [liboqs](https://github.com/open-quantum-safe/liboqs) — the Homebrew
bottle and vcpkg port both ship `FIZZ_HAVE_OQS=0`, so they negotiate classical
groups only.

This is a local development build. Paths below assume Linux + Homebrew
(`/home/linuxbrew/.linuxbrew`); adjust for your prefix.

## Prerequisites

```bash
brew install fizz liboqs    # fizz pulls folly, boost, glog, gflags, libsodium, double-conversion
git submodule update --init pybind11
```

- **C++20 is required** — current Folly (2026.06) dropped C++17.
- Fizz and Folly are versioned together. Building Fizz from source (below) must
  use the tag matching the Homebrew Folly bottle, or the ABI won't match.

## Classical build (no post-quantum)

The fastest path. Links the Homebrew Fizz bottle directly; negotiates X25519 /
P-256 but **not** `X25519MLKEM768`.

```bash
cmake -S .dev -B .dev/build -G Ninja \
  -DCMAKE_MODULE_PATH=/home/linuxbrew/.linuxbrew/opt/fizz/libexec/cmake \
  -DCMAKE_PREFIX_PATH=/home/linuxbrew/.linuxbrew
cmake --build .dev/build
cp .dev/build/_core*.so fizzpy/
```

## Post-quantum build (the differentiator)

### 1. Build Fizz from source against liboqs

Clone Fizz at the tag matching your Homebrew Folly (check `brew info folly`):

```bash
git clone --depth 1 --branch v2026.06.08.00 \
  https://github.com/facebookincubator/fizz .dev/fizz-src

cmake -S .dev/fizz-src/fizz -B .dev/fizz-build -G Ninja \
  -DCMAKE_INSTALL_PREFIX=$PWD/.dev/fizz-oqs \
  -DCMAKE_MODULE_PATH=$PWD/.dev/fizz-src/build/fbcode_builder/CMake \
  -DCMAKE_PREFIX_PATH="/home/linuxbrew/.linuxbrew;/home/linuxbrew/.linuxbrew/opt/liboqs;/home/linuxbrew/.linuxbrew/opt/libsodium" \
  -DBUILD_EXAMPLES=OFF -DBUILD_TESTS=OFF

cmake --build .dev/fizz-build --target install
```

`find_package(liboqs CONFIG)` inside Fizz auto-sets `FIZZ_HAVE_OQS` and links
`OQS::oqs`. `BUILD_EXAMPLES=OFF` is required: the bundled FizzTool fails to
compile under OpenSSL 3.6 (`-Werror` on the deprecated `EVP_PKEY_cmp`); the
library itself is fine.

### 2. Build `_core` against the OQS Fizz

The OQS install must come **first** on `CMAKE_PREFIX_PATH` so `find_package(fizz)`
resolves to it rather than the Homebrew bottle:

```bash
cmake -S .dev -B .dev/build-oqs -G Ninja \
  -DCMAKE_MODULE_PATH=/home/linuxbrew/.linuxbrew/opt/fizz/libexec/cmake \
  -DCMAKE_PREFIX_PATH="$PWD/.dev/fizz-oqs;/home/linuxbrew/.linuxbrew/opt/liboqs;/home/linuxbrew/.linuxbrew/opt/libsodium;/home/linuxbrew/.linuxbrew"
cmake --build .dev/build-oqs
cp .dev/build-oqs/_core*.so fizzpy/
```

The OQS-linked static Fizz is baked into `_core.so`; liboqs remains a runtime
shared dependency resolved via rpath from Homebrew.

## Verify

```bash
python -c "import fizzpy; print(fizzpy.get('https://www.cloudflare.com').tls)"
# group should be 'X25519MLKEM768', group_code 4588
```

## Tests

```bash
pip install pytest
pytest -m "not network"   # offline: parsing, config, hostname verification
pytest                    # includes live TLS integration (needs network)
```
