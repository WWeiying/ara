#include "q8_K-m4.h"
#include "qbs/qbs_abi.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

extern "C" bool m4_produce(const float *, void *, int64_t);
extern "C" bool m4_packed_produce(const float *, void *, int64_t);
extern "C" const float real_input[];

static constexpr size_t MaxK = 8192;
static constexpr size_t Payload = MaxK / 256 * 4 * QBS_Q8_K_BLOCK_BYTES;
alignas(64) static float input[4 * MaxK + 2], saved[4 * MaxK + 2];
alignas(64) static unsigned char reference[Payload + 160];
alignas(64) static unsigned char original[Payload + 160];
alignas(64) static unsigned char packed[Payload + 160];
static unsigned checks, domain_checks, current_kind;
static size_t current_k;

static void require(bool ok, const char *reason) {
    if (!ok) {
        std::printf("PACKED_EXTENT_FAIL check=%u k=%zu kind=%u reason=%s\n",
                    checks, current_k, current_kind, reason);
        std::exit(1);
    }
}
static void set_bits(float &value, uint32_t bits) { std::memcpy(&value, &bits, 4); }
static unsigned fc() { unsigned v; asm volatile("frcsr %0" : "=r"(v) :: "memory"); return v; }
static unsigned vc() { unsigned v; asm volatile("csrr %0,vcsr" : "=r"(v) :: "memory"); return v; }
static void state(unsigned f, unsigned v) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0" :: "r"(f), "r"(v) : "memory");
}

static void fill(unsigned kind, size_t k) {
    std::memset(input, 0, sizeof(input));
    for (size_t row = 0; row < 4; ++row) {
        for (size_t b = 0; b < k / 256; ++b) {
            float *x = input + 1 + row*k + b*256;
            for (size_t j = 0; j < 256; ++j) {
                const uint32_t sign = ((j + row + b) & 1) ? 0x80000000u : 0;
                switch (kind) {
                    case 0: x[j] = real_input[row*1536 + (b*256+j)%1536]; break;
                    case 1: x[j] = 0; break;
                    case 2: set_bits(x[j], sign | 0x3f800000u); break;
                    case 3: x[j] = j == 255 ? -127.0f : float(int(j%31)-15); break;
                    case 4: x[j] = j == 15 ? 127.0f : (j == 128 ? -127.0f : 0.25f); break;
                    case 5: set_bits(x[j], sign); break;
                    case 6: set_bits(x[j], sign | 0x08800000u); break;
                    case 7: set_bits(x[j], sign | 0x77000000u); break;
                    case 8: set_bits(x[j], sign | (j == 0 ? 0x3f800000u : 0x00800000u)); break;
                    case 9: set_bits(x[j], sign | (j == 0 ? 0x3f800000u : 1u)); break;
                    case 10: set_bits(x[j], sign | 0x08000000u); break;
                    case 11: set_bits(x[j], sign | 0x77800000u); break;
                }
            }
        }
    }
    std::memcpy(saved, input, sizeof(input));
}

static void compare(unsigned f, unsigned v) {
    const size_t offset = 64 + 4*(checks & 1);
    const size_t bytes = current_k / 256 * 4 * QBS_Q8_K_BLOCK_BYTES;
    std::memset(reference, 0xa5, sizeof(reference));
    std::memset(original, 0xa5, sizeof(original));
    std::memset(packed, 0xa5, sizeof(packed));
    state(f, v);
    ggml_quantize_mat_q8_K_4x1_ara_generic(input + 1, reference + offset, current_k);
    const unsigned rf = fc(), rv = vc();
    state(f, v);
    const bool first = m4_produce(input + 1, original + offset, current_k);
    const unsigned of = fc(), ov = vc();
    state(f, v);
    const bool second = m4_packed_produce(input + 1, packed + offset, current_k);
    const unsigned pf = fc(), pv = vc();
    const bool expected = current_k && !(f >> 5) && current_kind < 9;
    require(first == expected && second == expected, "fallback_selection");
    if (rf != pf || rv != pv || rf != of || rv != ov) {
        std::printf("STATE f=%u v=%u generic=%u/%u original=%u/%u packed=%u/%u\n",
                    f, v, rf, rv, of, ov, pf, pv);
        require(false, "architectural_state");
    }
    for (size_t i = 0; i < sizeof(reference); ++i) {
        if (reference[i] != packed[i] || reference[i] != original[i]) {
            std::printf("BYTE offset=%zu generic=%u original=%u packed=%u\n",
                        i, reference[i], original[i], packed[i]);
            require(false, "generic_bytes");
        }
        if (i < offset || i >= offset + bytes) require(packed[i] == 0xa5, "canary");
    }
    require(std::memcmp(input, saved, sizeof(input)) == 0, "input_modified");
    ++checks;
}

int main() {
    for (size_t k : {0u, 256u, 512u, 768u, 1536u, 3072u, 6144u, 8192u}) {
        current_k = k;
        for (unsigned kind = 0; kind < 12; ++kind) {
            current_kind = kind;
            fill(kind, k);
            compare(0, 0);
            compare(17, 7);
            for (unsigned frm = 1; frm <= 4; ++frm) compare((frm << 5) | 17, frm);
        }
    }
    // NaN/Inf are outside the existing generic quantizer's input contract.
    // Test their admission only; do not claim the generic produces valid bytes.
    current_k = 256;
    for (uint32_t bits : {0x7fc12345u, 0x7f800001u, 0x7f800000u, 0xff800000u}) {
        for (size_t position : {0u, 15u, 16u, 127u, 128u, 255u, 1023u}) {
            fill(2, 256);
            set_bits(input[1 + position], bits);
            state(17, 5);
            const bool admitted = ggml_riscv_q8_K_m4::vector_domain(input + 1, 256);
            require(!admitted && fc() == 17 && vc() == 5, "nonfinite_domain_or_state");
            ++domain_checks;
        }
    }
    require(checks == 576 && domain_checks == 28, "test_extent");
    std::printf("PACKED_EXTENT_PASS checks=%u domain_checks=%u shapes=8 patterns=12 max_k=8192\n",
                checks, domain_checks);
    return 0;
}
