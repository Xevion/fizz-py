# Manylinux base image with the folly + fizz + liboqs tree prebuilt, so wheel
# builds skip the ~40-min source build and just compile _core against it. Rebuilt
# by the deps_image job in .github/workflows/wheels.yml when build_fizz_deps.py or
# fizz-tag.txt changes. The dep prefixes land in $FIZZPY_BUILD_INFO/prefix.txt,
# which CMake reads at configure time (see CMakeLists.txt).
ARG MANYLINUX_IMAGE=quay.io/pypa/manylinux_2_28_x86_64:latest
FROM ${MANYLINUX_IMAGE}

ENV GETDEPS_SCRATCH=/opt/fizz-deps \
    FIZZPY_BUILD_INFO=/opt/fizzpy-build \
    FIZZ_SRC=/opt/fizz-src

# The script reads the pin from fizz-tag.txt beside itself.
COPY scripts/build_fizz_deps.py scripts/fizz-tag.txt /opt/
RUN python3 /opt/build_fizz_deps.py
