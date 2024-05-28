cmake_minimum_required(VERSION 3.10)

project(FizzPy)

if(DEFINED ENV{VCPKG_ROOT} AND NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")
endif()

MESSAGE(STATUS "Using toolchain file: ${CMAKE_TOOLCHAIN_FILE}")

find_package(fizz CONFIG REQUIRED)

add_subdirectory(pybind11)
pybind11_add_module(fizzpy main.cpp)

target_link_libraries(fizzpy PRIVATE fizz::fizz)