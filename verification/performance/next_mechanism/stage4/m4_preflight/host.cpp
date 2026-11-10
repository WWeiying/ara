#include "m4_preflight.h"
#include "q8_K-prepared-cache.h"
#include <cstdio>
#include <cstring>
#include <initializer_list>

static unsigned calls;
extern "C" void ggml_quantize_mat_q8_K_4x1_ara_generic(const float *, void *out, int64_t k) {
    ++calls;
    std::memset(out, 0x39, k/256*sizeof(block_q8_Kx4));
}
int main() {
    static float x[4*6400];
    static unsigned char y[25*sizeof(block_q8_Kx4)+128];
    for (int k : {0, 256, 6144, 6400}) {
        std::memset(y, 0xa5, sizeof(y));
        if (qbs_experimental_m4_preflight::quantize(x, y+64, k)) return 1;
        for (size_t i = 0; i < sizeof(y); ++i) {
            const unsigned want = i >= 64 && i < 64+k/256*sizeof(block_q8_Kx4) ? 0x39 : 0xa5;
            if (y[i] != want) return 2;
        }
    }
    if (calls != 4 || sizeof(qbs_experimental_m4_preflight::maxima) != 384) return 3;
    ggml_riscv_q8_K_cache::value_cache<> cache;
    ggml_riscv_q8_K_cache::key key;
    key.k = 256; key.producer_tag = 3;
    unsigned flags = 0;
    constexpr size_t in = 4*256*sizeof(float), out = sizeof(block_q8_Kx4);
    if (!cache.put(key, x, in, y, out, 17) || !cache.get(key, x, in, y+out, out, flags) || flags != 17) return 4;
    key.producer_tag = qbs_experimental_m4_preflight::producer_tag;
    if (cache.get(key, x, in, y+out, out, flags)) return 5;
    if (!cache.put(key, x, in, y, out, 9)) return 6;
    x[4] = 1;
    if (cache.get(key, x, in, y+out, out, flags)) return 7;
    x[4] = 0;
    if (!cache.get(key, x, in, y+out, out, flags) || flags != 9) return 8;
    key.frm = 1;
    if (cache.get(key, x, in, y+out, out, flags)) return 9;
    key.frm = 0; key.vstart = 1;
    if (cache.get(key, x, in, y+out, out, flags)) return 10;
    key.vstart = 0; cache.clear();
    if (cache.get(key, x, in, y+out, out, flags) || cache.retained_bytes()) return 11;
    ggml_riscv_q8_K_cache::value_cache<> no_memory([](size_t) -> uint8_t * { return nullptr; });
    if (no_memory.put(key, x, in, y, out, 0) || no_memory.statistics().allocation_failures != 1) return 12;
    std::puts("STAGE4_M4_HOST_PASS non_rvv_fallback=4 metadata_bytes=384 cache_checks=9");
}
