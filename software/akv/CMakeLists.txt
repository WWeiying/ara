cmake_minimum_required(VERSION 3.16)
project(akv_runtime VERSION 1.0.0 LANGUAGES C)

include(GNUInstallDirs)

add_library(akv_runtime STATIC
    src/akv_runtime.c
    src/akv_native_riscv.c
    src/akv_v2_native_riscv.c
    src/akv_v2_reference.c)
add_library(akv::runtime ALIAS akv_runtime)
target_include_directories(akv_runtime PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
target_compile_features(akv_runtime PUBLIC c_std_11)
set_target_properties(akv_runtime PROPERTIES
    EXPORT_NAME runtime
    POSITION_INDEPENDENT_CODE ON)

set(AKV_NATIVE_KERNEL_DEFAULT OFF)
if (CMAKE_SYSTEM_PROCESSOR MATCHES "^(riscv|riscv64)$")
    set(AKV_NATIVE_KERNEL_DEFAULT ON)
endif()
option(AKV_BUILD_NATIVE_KERNEL "Build the native RVV AKV attention kernel" ${AKV_NATIVE_KERNEL_DEFAULT})
if (AKV_BUILD_NATIVE_KERNEL)
    enable_language(ASM)
    target_sources(akv_runtime PRIVATE
        src/akv_attention_rvv.S
        src/akv_v2_attention_rvv.S)
endif()

install(TARGETS akv_runtime EXPORT akvRuntimeTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(DIRECTORY include/akv DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT akvRuntimeTargets
    NAMESPACE akv::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/akv_runtime)

option(AKV_BUILD_TESTS "Build AKV runtime host tests" OFF)
if (AKV_BUILD_TESTS)
    enable_testing()
    add_executable(akv_runtime_test tests/akv_runtime_test.c)
    target_link_libraries(akv_runtime_test PRIVATE akv::runtime)
    add_test(NAME akv_runtime_test COMMAND akv_runtime_test)
endif()
