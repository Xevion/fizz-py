cmake_minimum_required(VERSION 3.15...3.27)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

project(
  ${SKBUILD_PROJECT_NAME}
  VERSION ${SKBUILD_PROJECT_VERSION}
  LANGUAGES CXX)

# Fizz's CMake config pulls in its bundled FindSodium.cmake. Homebrew installs
# it under libexec/cmake; make that discoverable for local (non-vcpkg) builds.
# Override with -DFIZZ_CMAKE_MODULE_DIR=... if your install differs.
set(FIZZ_CMAKE_MODULE_DIR "/home/linuxbrew/.linuxbrew/opt/fizz/libexec/cmake"
    CACHE PATH "Directory containing Fizz's bundled CMake find-modules")
if(EXISTS "${FIZZ_CMAKE_MODULE_DIR}")
  list(APPEND CMAKE_MODULE_PATH "${FIZZ_CMAKE_MODULE_DIR}")
endif()

if(DEFINED ENV{VCPKG_ROOT} AND NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake"
      CACHE STRING "")
endif()

message(STATUS "Using compiler: ${CMAKE_CXX_COMPILER}")

set(PYBIND11_NEWPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)
find_package(fizz CONFIG REQUIRED)

pybind11_add_module(_core _core.cpp)
target_link_libraries(_core PRIVATE fizz::fizz)

# _core.cpp drives connections on a folly::ScopedEventBaseThread, but fizz itself
# never uses that type — so when folly is a static archive (e.g. getdeps
# --shared-lib portable wheels), its object never makes it into libfizz and the
# symbol is undefined at import. Link the component directly when folly exposes
# it as a discrete target; classic shared-folly builds (Homebrew) export it from
# libfolly already and skip this.
if(TARGET Folly::folly_io_async_scoped_event_base_thread)
  target_link_libraries(_core PRIVATE Folly::folly_io_async_scoped_event_base_thread)
endif()

install(TARGETS _core LIBRARY DESTINATION fizzpy)
