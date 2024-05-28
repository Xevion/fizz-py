cmake_minimum_required(VERSION 3.10)

project(FizzPyh)

find_package(fizz CONFIG REQUIRED)

add_executable(Fizz main.cpp)

target_link_libraries(Fizz PRIVATE fizz::fizz)