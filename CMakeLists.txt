cmake_minimum_required(VERSION 3.16)
project(numlang LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(numlangc src/main.cpp)
target_compile_options(numlangc PRIVATE -Wall -Wextra -Wpedantic)

find_package(Python3 REQUIRED COMPONENTS Interpreter)
enable_testing()
add_test(NAME compiler_smoke COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/smoke_cpp.py $<TARGET_FILE:numlangc> ${CMAKE_C_COMPILER})
add_test(NAME legacy_reference_tests COMMAND ${Python3_EXECUTABLE} -m pytest -q tests/test_compiler.py)
add_test(NAME capability_matrix COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/scripts/check_capabilities.py)
set_tests_properties(compiler_smoke legacy_reference_tests capability_matrix PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
