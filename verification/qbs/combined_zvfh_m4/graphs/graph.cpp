// Keep the reviewed scalar/decode oracle and all 16 shapes unchanged.
#if !defined(__riscv_vector) || !defined(__riscv_zfh) || !defined(__riscv_zvfh)
#error "Graph gate requires the actual combined RVV/Zfh/Zvfh ISA"
#endif
#include "../../ggml_m4_prepare_production/graph.cpp"
