cmake_minimum_required(VERSION 3.16)
project(qbs_runtime VERSION 1.0.0 LANGUAGES C)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

add_library(qbs_runtime STATIC
    src/qbs_runtime.c
    src/qbs_native_riscv.c)
add_library(qbs::runtime ALIAS qbs_runtime)
target_include_directories(qbs_runtime PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
target_compile_features(qbs_runtime PUBLIC c_std_11)
set_target_properties(qbs_runtime PROPERTIES
    EXPORT_NAME runtime
    POSITION_INDEPENDENT_CODE ON)

configure_package_config_file(
    cmake/qbs_runtimeConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/qbs_runtimeConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/qbs_runtime)
write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/qbs_runtimeConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion)

install(TARGETS qbs_runtime EXPORT qbsRuntimeTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(DIRECTORY include/qbs DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT qbsRuntimeTargets
    NAMESPACE qbs::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/qbs_runtime)
install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/qbs_runtimeConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/qbs_runtimeConfigVersion.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/qbs_runtime)

option(QBS_BUILD_TESTS "Build QBS runtime host tests" OFF)
if (QBS_BUILD_TESTS)
    enable_testing()
    add_executable(qbs_runtime_test tests/qbs_runtime_test.c)
    target_link_libraries(qbs_runtime_test PRIVATE qbs_runtime)
    add_test(NAME qbs_runtime_test COMMAND qbs_runtime_test)
endif()

option(QBS_BUILD_EXAMPLES "Build QBS runtime adapter examples" OFF)
if (QBS_BUILD_EXAMPLES)
    add_executable(qbs_runtime_adapter_example examples/runtime_adapter.c)
    target_link_libraries(qbs_runtime_adapter_example PRIVATE qbs::runtime)
endif()
