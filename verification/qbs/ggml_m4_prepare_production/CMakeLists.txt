cmake_minimum_required(VERSION 3.16)
project(qbs_m4_prepare_production LANGUAGES C CXX)

# Reuse the sealed toolchain/runtime configuration, with a private binary tree.
add_subdirectory("../ggml_tile_context" "${CMAKE_CURRENT_BINARY_DIR}/tile-support" EXCLUDE_FROM_ALL)
get_filename_component(QBS_RUNTIME "${CMAKE_CURRENT_LIST_DIR}/../../../software/qbs" REALPATH)
foreach(kind IN ITEMS native graph)
    add_executable(qbs-m4-prepare-${kind} ${kind}.cpp)
    set_target_properties(qbs-m4-prepare-${kind} PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
    target_compile_features(qbs-m4-prepare-${kind} PRIVATE cxx_std_17)
    target_compile_options(qbs-m4-prepare-${kind} PRIVATE
        -UNDEBUG -fno-fast-math -ffp-contract=off -fno-tree-vectorize -Wall -Wextra -Werror)
    target_include_directories(qbs-m4-prepare-${kind} SYSTEM PRIVATE
        "${LLAMA_SOURCE_DIR}/ggml/src" "${LLAMA_SOURCE_DIR}/ggml/src/ggml-cpu")
    target_include_directories(qbs-m4-prepare-${kind} PRIVATE "${QBS_RUNTIME}/include")
    target_link_libraries(qbs-m4-prepare-${kind} PRIVATE ggml ggml-cpu)
endforeach()
add_executable(qbs-m4-prepare-init init.c)
set_target_properties(qbs-m4-prepare-init PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
target_compile_options(qbs-m4-prepare-init PRIVATE -Wall -Wextra -Werror)
add_executable(qbs-m4-prepare-native-init init.c)
set_target_properties(qbs-m4-prepare-native-init PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
target_compile_definitions(qbs-m4-prepare-native-init PRIVATE M4_NATIVE_ONLY=1)
target_compile_options(qbs-m4-prepare-native-init PRIVATE -Wall -Wextra -Werror)

foreach(mode IN ITEMS norvv fastmath)
    add_library(qbs-m4-prepare-${mode} OBJECT fallback.cpp)
    target_compile_features(qbs-m4-prepare-${mode} PRIVATE cxx_std_17)
    target_include_directories(qbs-m4-prepare-${mode} SYSTEM PRIVATE
        "${LLAMA_SOURCE_DIR}/ggml/include" "${LLAMA_SOURCE_DIR}/ggml/src"
        "${LLAMA_SOURCE_DIR}/ggml/src/ggml-cpu")
endforeach()
target_compile_options(qbs-m4-prepare-norvv PRIVATE -march=rv64gc)
target_compile_options(qbs-m4-prepare-fastmath PRIVATE -ffast-math)
