// Only the archived graph fixture is included. Its original main is not run.
#ifndef THREAD_FLAGS_FIXTURE
#error "Supply the preserved failed-run fixture path"
#endif
#define main sealed_grouped_graph_main
#include THREAD_FLAGS_FIXTURE
#undef main

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    option("GGML_RISCV_QBS", "1");
    option("GGML_RISCV_QBS_EMULATE", "0");
    option("GGML_RISCV_AKV", "0");
    option("GGML_RISCV_AKV_EMULATE", "0");
    option("GGML_RISCV_AKV_TRACE", "1");
    option("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1");
    option("GGML_RISCV_AKV_QUANT_KV", "0");
    grouped_option(0);
    ggml_cpu_init();
    const capture data(true);
    graph_fixture fixture(data, true, true);
    fixture.prefix(128);
    result reference{};
    std::puts("THREAD_FLAGS_BEGIN kind=q4_0 layout=token_major visible=128 threads=2 calls=16 quant_kv=0 grouped=unset initial_fcsr=8 initial_vcsr=5");
    for (unsigned call = 0; call < 16; ++call) {
        const result actual = fixture.compute(2);
        if (call) same_bits(actual, reference);
        else reference = actual;
        std::printf("THREAD_FLAGS_CALL call=%u outputs=1536 fcsr=%lu vcsr=%lu digest=%016llx exact=1\n",
                    call, static_cast<unsigned long>(actual.fcsr),
                    static_cast<unsigned long>(actual.vcsr),
                    static_cast<unsigned long long>(digest(actual.output.data(), OUTPUT_BYTES)));
    }
    std::puts("THREAD_FLAGS_COMPLETE calls=16 outputs_each=1536 all_bits_equal=1 quant_kv=0 grouped=unset performance=not_measured");
    return 0;
}
