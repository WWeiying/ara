cmake_minimum_required(VERSION 3.16)
project(qbs_m4_production_csr LANGUAGES C CXX)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
add_subdirectory("../ggml_tile_context" "${CMAKE_CURRENT_BINARY_DIR}/tile-support" EXCLUDE_FROM_ALL)
add_executable(qbs-m4-production-csr test.cpp)
set_target_properties(qbs-m4-production-csr PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}" INTERPROCEDURAL_OPTIMIZATION FALSE)
target_compile_features(qbs-m4-production-csr PRIVATE cxx_std_17)
target_compile_options(qbs-m4-production-csr PRIVATE
    -UNDEBUG -fno-lto -fno-fast-math -ffp-contract=off -fno-tree-vectorize -Wall -Wextra -Werror)
target_include_directories(qbs-m4-production-csr SYSTEM PRIVATE
    "${LLAMA_SOURCE_DIR}/ggml/src" "${LLAMA_SOURCE_DIR}/ggml/src/ggml-cpu")
target_link_options(qbs-m4-production-csr PRIVATE -fno-lto "-Wl,-Map=${CMAKE_BINARY_DIR}/csr.map,--cref")
target_link_libraries(qbs-m4-production-csr PRIVATE ggml ggml-cpu)
add_executable(qbs-m4-production-csr-init init.c)
set_target_properties(qbs-m4-production-csr-init PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
target_compile_options(qbs-m4-production-csr-init PRIVATE -Wall -Wextra -Werror)
