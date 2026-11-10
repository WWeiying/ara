            if (GGML_RISCV_AKV_RESIDENT)
                if (NOT EXISTS "${GGML_RISCV_AKV_RUNTIME_DIR}/experimental/resident_attention/executor.h")
                    message(FATAL_ERROR "Resident opt-in requires the reviewed experimental SDK")
                endif()
                target_compile_definitions(${GGML_CPU_NAME} PRIVATE
                    GGML_AKV_RESIDENT=1 AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1
                    AKV_EXPERIMENTAL_RESIDENT_FEATURES_V2=0 AKV_REFILL_OVERLAP=0)
                target_include_directories(${GGML_CPU_NAME} PRIVATE
                    ${GGML_RISCV_AKV_RUNTIME_DIR}/experimental
                    ${CMAKE_CURRENT_SOURCE_DIR}/ggml-cpu/arch/riscv)
                list(APPEND GGML_CPU_SOURCES
                    ggml-cpu/arch/riscv/platform.c
                    ggml-cpu/arch/riscv/read_state.S
                    ggml-cpu/arch/riscv/entry.c
                    ${GGML_RISCV_AKV_RUNTIME_DIR}/experimental/resident_attention/qk.S
                    ${GGML_RISCV_AKV_RUNTIME_DIR}/experimental/resident_attention/pv.S)
                if (CMAKE_C_COMPILER_ID STREQUAL "GNU")
                    set_property(SOURCE ggml-cpu/arch/riscv/platform.c ggml-cpu/arch/riscv/entry.c
                        APPEND PROPERTY COMPILE_OPTIONS
                        -fno-tree-vectorize -fno-tree-slp-vectorize -ffreestanding -fno-builtin)
                    set_property(SOURCE ggml-cpu/arch/riscv/akv.cpp
                        APPEND PROPERTY COMPILE_OPTIONS
                        -fno-tree-vectorize -fno-tree-slp-vectorize -fno-fast-math -ffp-contract=off)
                elseif (CMAKE_C_COMPILER_ID MATCHES "Clang")
                    set_property(SOURCE ggml-cpu/arch/riscv/platform.c ggml-cpu/arch/riscv/entry.c
                        APPEND PROPERTY COMPILE_OPTIONS
                        -fno-vectorize -fno-slp-vectorize -ffreestanding -fno-builtin)
                    set_property(SOURCE ggml-cpu/arch/riscv/akv.cpp
                        APPEND PROPERTY COMPILE_OPTIONS
                        -fno-vectorize -fno-slp-vectorize -fno-fast-math -ffp-contract=off)
                else()
                    message(FATAL_ERROR "Resident guard requires reviewed scalar compiler flags")
                endif()
            endif()
