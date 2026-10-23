// Reuse the sealed independent scalar/decode oracle, not a second kernel.
#define main tile_context_graph_main
#include "../ggml_tile_context/test.cpp"
#undef main

int main() {
    const char * optin = std::getenv("GGML_RISCV_QBS_M4_PREPARE");
    require(optin && (!std::strcmp(optin, "0") || !std::strcmp(optin, "1")),
            "explicit_m4_prepare_policy_required");
    require(enabled("GGML_RISCV_QBS_TRACE_M4_PREPARE"), "preparation_path_trace_required");
    unsigned frm;
    asm volatile("frrm %0" : "=r"(frm) : : "memory");
    require(frm == 0, "graph_requires_rne");
    return tile_context_graph_main();
}
