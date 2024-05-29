cmake_minimum_required(VERSION 3.15...3.26)

project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

if (NOT DEFINED ENV{VCPKG_ROOT} AND NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  message(FATAL_ERROR "Please set VCPKG_ROOT to the root of your vcpkg installation, or set CMAKE_TOOLCHAIN_FILE to the path to the vcpkg.cmake file")
endif()

if(DEFINED ENV{VCPKG_ROOT} AND NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")
endif()

message(STATUS "Using toolchain file: ${CMAKE_TOOLCHAIN_FILE}")

set(PYBIND11_NEWPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)
find_package(fizz CONFIG REQUIRED)

pybind11_add_module(fizzpy main.cpp)

target_link_libraries(fizzpy PRIVATE fizz::fizz)

install(TARGETS fizzpy LIBRARY DESTINATION .)