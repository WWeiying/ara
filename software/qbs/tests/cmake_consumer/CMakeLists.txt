cmake_minimum_required(VERSION 3.16)
project(qbs_runtime_consumer LANGUAGES C)

find_package(qbs_runtime CONFIG REQUIRED)

add_executable(qbs_runtime_consumer main.c)
target_link_libraries(qbs_runtime_consumer PRIVATE qbs::runtime)
