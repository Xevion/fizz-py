cmake_minimum_required(VERSION 3.15...3.27)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

project(
  ${SKBUILD_PROJECT_NAME}
  VERSION ${SKBUILD_PROJECT_VERSION}
  LANGUAGES CXX)

# Wheels target Linux, macOS, and Windows. Other platforms stop here before the
# (~40 min) folly + fizz + liboqs source build an sdist install would attempt.
if(NOT CMAKE_SYSTEM_NAME MATCHES "^(Linux|Darwin|Windows)$")
  message(
    FATAL_ERROR
    "fizzpy publishes prebuilt wheels for Linux, macOS, and Windows; "
    "${CMAKE_SYSTEM_NAME} is not supported. Building from source needs the Fizz "
    "toolchain — see BUILDING.md "
    "(https://github.com/Xevion/fizz-py/blob/master/BUILDING.md).")
endif()

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

# Portable-wheel builds: scripts/build_fizz_deps.py (cibuildwheel before-all)
# writes the getdeps install prefixes and fizz's find-module dir here. Read them
# at configure time rather than as a CIBW environment substitution, which would
# evaluate before before-all has produced the files. Skipped for local builds,
# which pass -DCMAKE_PREFIX_PATH directly (see BUILDING.md).
if(DEFINED ENV{FIZZPY_BUILD_INFO})
  set(_info "$ENV{FIZZPY_BUILD_INFO}")
  if(EXISTS "${_info}/prefix.txt")
    file(STRINGS "${_info}/prefix.txt" _fizz_prefix)
    list(APPEND CMAKE_PREFIX_PATH ${_fizz_prefix})
  endif()
  if(EXISTS "${_info}/module_dir.txt")
    file(STRINGS "${_info}/module_dir.txt" _fizz_modules)
    list(APPEND CMAKE_MODULE_PATH ${_fizz_modules})
  endif()
endif()

# pybind11 is pip-installed (locally, or by before-build in wheel builds); add its
# CMake config so find_package locates it without a CIBW env substitution.
# Development.Module must be in this first find_package: pybind11's NewTools skips
# its own Python discovery once Python_FOUND is set, so python_add_library (from
# Development.Module) would otherwise never be defined.
find_package(Python COMPONENTS Interpreter Development.Module QUIET)
if(Python_Interpreter_FOUND)
  execute_process(
    COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
    OUTPUT_VARIABLE _pybind11_cmakedir
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET)
  if(_pybind11_cmakedir)
    list(APPEND CMAKE_PREFIX_PATH "${_pybind11_cmakedir}")
  endif()
endif()

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

# Static deps need Windows system libs their getdeps configs don't propagate as
# interface links: bcrypt (RNG: libevent, liboqs), crypt32 (OpenSSL cert store),
# ws2_32 (sockets), iphlpapi (folly GetAdaptersAddresses), advapi32 (OpenSSL/
# libevent registry + RNG fallback). Link them on the consumer.
if(WIN32)
  target_link_libraries(_core PRIVATE bcrypt crypt32 ws2_32 iphlpapi advapi32)
endif()

install(TARGETS _core LIBRARY DESTINATION fizzpy)
