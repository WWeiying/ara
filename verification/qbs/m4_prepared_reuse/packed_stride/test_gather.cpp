#include "strided_input.h"
#include <cstdio>
#include <cstdlib>
#include <vector>

static unsigned checks;
static void need(bool ok) { if (!ok) std::abort(); }

template <size_t Rows, size_t Block>
static void test() {
    constexpr size_t OutputBytes = Rows*(Block+4);
    for (size_t blocks : {0u, 1u, 2u, 3u, 24u, 32u}) {
        const size_t k = blocks*Block;
        for (size_t element_stride : {4u, 8u, 20u}) {
            for (size_t padding : {0u, 4u, 60u}) {
                const size_t row_stride = k*element_stride + padding;
                std::vector<unsigned char> input(68 + Rows*row_stride + 64, 0x7b);
                std::vector<unsigned char> actual(64 + blocks*OutputBytes + 64, 0xa5);
                auto expected = actual;
                for (size_t row = 0; row < Rows; ++row) {
                    for (size_t col = 0; col < k; ++col) {
                        const uint32_t word = 0x3f000000u + uint32_t(row*8192 + col);
                        std::memcpy(input.data()+68+row*row_stride+col*element_stride, &word, 4);
                    }
                }
                const auto saved = input;
                size_t calls = 0;
                ggml_qbs_strided_input::quantize<Rows, Block, OutputBytes>(
                    reinterpret_cast<const char *>(input.data()+68), actual.data()+64, k,
                    element_stride, row_stride,
                    [&](const float *values, void *out, int64_t count) {
                        need(count == int64_t(Block) && calls < blocks);
                        need(out == actual.data()+64+calls*OutputBytes);
                        for (size_t row = 0; row < Rows; ++row) {
                            for (size_t col = 0; col < Block; ++col) {
                                const uint32_t expected_word = 0x3f000000u + uint32_t(row*8192 + calls*Block + col);
                                uint32_t word;
                                std::memcpy(&word, values+row*Block+col, 4);
                                need(word == expected_word);
                            }
                        }
                        std::memset(out, int(calls+1), OutputBytes);
                        std::memset(expected.data()+64+calls*OutputBytes, int(calls+1), OutputBytes);
                        ++calls;
                    });
                need(calls == blocks && actual == expected && input == saved);
                ++checks;
            }
        }
    }
}

int main() {
    test<1,32>(); test<4,32>(); test<1,256>(); test<4,256>();
    need(checks == 216);
    std::printf("STRIDED_GATHER_PASS checks=%u\n", checks);
}
