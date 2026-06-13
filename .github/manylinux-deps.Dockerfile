# Manylinux base image with the folly + fizz + liboqs tree prebuilt, so wheel
# builds skip the ~40-min source build and just compile _core against it. Rebuilt
# by .github/workflows/manylinux-image.yml when build_fizz_deps.py or FIZZ_TAG
# changes. The dep prefixes land in $FIZZPY_BUILD_INFO/prefix.txt, which CMake
# reads at configure time (see CMakeLists.txt).
ARG MANYLINUX_IMAGE=quay.io/pypa/manylinux_2_28_x86_64:latest
FROM ${MANYLINUX_IMAGE}

ARG FIZZ_TAG=v2026.06.08.00
ENV FIZZ_TAG=${FIZZ_TAG} \
    GETDEPS_SCRATCH=/opt/fizz-deps \
    FIZZPY_BUILD_INFO=/opt/fizzpy-build \
    FIZZ_SRC=/opt/fizz-src

COPY scripts/build_fizz_deps.py /opt/build_fizz_deps.py
RUN python3 /opt/build_fizz_deps.py
