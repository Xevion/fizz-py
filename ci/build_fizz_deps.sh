#!/usr/bin/env bash
# cibuildwheel `before-all`: build the folly + fizz + liboqs dependency tree
# once per manylinux container as static-PIC archives that the _core extension
# links in wholesale, producing a single self-contained .so. Because liboqs is a
# fizz dependency in fizz's own getdeps manifest, the resulting fizz has
# FIZZ_HAVE_OQS=1 — i.e. real post-quantum support.
#
# Outputs (read by the per-wheel build via CIBW environment):
#   $FIZZPY_BUILD_INFO/prefix.txt      semicolon-joined CMAKE_PREFIX_PATH
#   $FIZZPY_BUILD_INFO/module_dir.txt  dir holding fizz's bundled find-modules
set -euxo pipefail

# Pin fizz to a release whose getdeps manifests pin a matching folly. liboqs is
# pinned by fizz's own manifest, so post-quantum support travels with the tag.
FIZZ_TAG="${FIZZ_TAG:-v2026.06.08.00}"
FIZZ_SRC="${FIZZ_SRC:-/opt/fizz-src}"
SCRATCH="${GETDEPS_SCRATCH:-/opt/fizz-deps}"
OUT="${FIZZPY_BUILD_INFO:-/opt/fizzpy-build}"

# AlmaLinux 8's system GCC (~8.5) is too old for folly's C++20; manylinux_2_28
# ships gcc-toolset-14. Activate it before any compilation.
source /opt/rh/gcc-toolset-14/enable

# getdeps bootstraps its own CMake (needs OpenSSL/zlib up front); folly's link
# interface references system libaio by absolute path. Install all before build.
yum install -y git openssl-devel zlib-devel libaio-devel libunwind-devel

rm -rf "$FIZZ_SRC"
git clone --depth 1 --branch "$FIZZ_TAG" \
  https://github.com/facebookincubator/fizz "$FIZZ_SRC"

GETDEPS="$FIZZ_SRC/build/fbcode_builder/getdeps.py"

# Build everything as static-PIC and link the whole tree into _core, rather than
# using --shared-lib. --shared-lib makes fizz a shared libfizz.so with folly
# baked in; _core would then link folly a SECOND time via fizz's cmake interface,
# so folly's gflags flags/singletons register twice and gflags aborts at import.
# A single static-PIC link keeps exactly one copy of folly. -fPIC handles the
# autotools deps (libsodium, xz, …); CMAKE_POSITION_INDEPENDENT_CODE the cmake
# ones (folly, fizz, glog, …). --allow-system-packages uses the system
# OpenSSL/zlib rather than rebuilding them.
export CFLAGS="-fPIC ${CFLAGS:-}"
export CXXFLAGS="-fPIC ${CXXFLAGS:-}"
PIC='{"CMAKE_POSITION_INDEPENDENT_CODE": "ON"}'

python3 "$GETDEPS" --scratch-path "$SCRATCH" build fizz --extra-cmake-defines "$PIC" \
  --src-dir="$FIZZ_SRC" --allow-system-packages --no-tests

mkdir -p "$OUT"
python3 "$GETDEPS" --scratch-path "$SCRATCH" show-inst-dir --recursive fizz --extra-cmake-defines "$PIC" \
  --src-dir="$FIZZ_SRC" --allow-system-packages | paste -sd';' > "$OUT/prefix.txt"

# fizz/folly use bundled find-modules (FindSodium, FindZstd, …) that live in the
# fizz source tree rather than installed config packages.
echo "$FIZZ_SRC/build/fbcode_builder/CMake" > "$OUT/module_dir.txt"

echo "fizz dependency tree built; prefix written to $OUT/prefix.txt"
