// Independent ordinary host-GGML graph reference. No QBS runtime or oracle.
#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"

#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

static void require(bool ok, const char * reason) {
    if (!ok) {
        std::fprintf(stderr, "TAIL_GOLD_FAIL reason=%s\n", reason);
        std::exit(1);
    }
}

static std::vector<unsigned char> load(const std::string & path, size_t size) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    require(stream && stream.tellg() == static_cast<std::streamoff>(size), "input_extent");
    stream.seekg(0);
    std::vector<unsigned char> data(size);
    stream.read(reinterpret_cast<char *>(data.data()), static_cast<std::streamsize>(size));
    require(stream.good() && stream.gcount() == static_cast<std::streamsize>(size), "input_read");
    return data;
}

int main(int argc, char ** argv) {
    require(argc == 4, "usage_kind_capture_directory_output_directory");
    const std::string kind = argv[1], directory = argv[2], output_directory = argv[3];
    require(kind == "q8_0" || kind == "q4_0", "key_type");
    static_assert(sizeof(float) == 4, "F32 output required");
    const uint16_t endian = 1;
    require(*reinterpret_cast<const unsigned char *>(&endian) == 1, "little_endian_host_required");
    require(std::fesetround(FE_TONEAREST) == 0, "host_rounding_mode");
    ggml_cpu_init();
    ggml_init_params init{};
    init.mem_size = 4 * 1024 * 1024;
    init.no_alloc = true;
    auto * ctx = ggml_init(init);
    require(ctx != nullptr, "context_allocation");
    auto * q = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, 128, 1, 12, 1);
    auto * k = ggml_new_tensor_4d(ctx, kind == "q4_0" ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0, 128, 256, 2, 1);
    auto * v = ggml_new_tensor_4d(ctx, GGML_TYPE_Q8_0, 128, 256, 2, 1);
    auto * mask = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, 256, 1, 1, 1);
    const uint32_t scale_bits = UINT32_C(0x3db504f3);
    float scale;
    std::memcpy(&scale, &scale_bits, sizeof(scale));
    auto * dst = ggml_flash_attn_ext(ctx, q, k, v, mask, scale, 0, 0);
    auto * graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, dst);
    require(ggml_graph_n_nodes(graph) == 1 && ggml_graph_node(graph, 0) == dst, "ordinary_graph_shape");
    auto buffer = ggml_backend_alloc_ctx_tensors_from_buft(ctx, ggml_backend_cpu_buffer_type());
    require(buffer != nullptr, "tensor_allocation");
    require(dst->ne[0] == 128 && dst->ne[1] == 12 && dst->ne[2] == 1 && dst->ne[3] == 1 &&
            ggml_nbytes(dst) == 6144 && ggml_is_contiguous(dst), "output_shape");
    ggml_tensor * inputs[] = {q, k, v, mask};
    const char * files[] = {"attn_q_input-0.bin", "attn_k_input-0.bin", "attn_v_input-0.bin", "attn_mask_input-0.bin"};
    std::vector<unsigned char> originals[4];
    for (unsigned i = 0; i < 4; ++i) {
        require(ggml_is_contiguous(inputs[i]), "input_must_remain_contiguous");
        originals[i] = load(directory + "/" + files[i], ggml_nbytes(inputs[i]));
        ggml_backend_tensor_set(inputs[i], originals[i].data(), 0, originals[i].size());
    }
    for (unsigned token = 0; token < 256; ++token) {
        uint16_t bits;
        std::memcpy(&bits, originals[3].data() + token * 2, 2);
        require(bits == (token < 128 ? 0 : UINT16_C(0xfc00)), "original_mask_not_visible128");
    }
    const auto captured_bytes = load(directory + "/kqv_out-0.bin", 6144);
    std::vector<float> captured(1536), output(1536);
    std::memcpy(captured.data(), captured_bytes.data(), captured_bytes.size());
    for (unsigned visible : {128u, 5u, 33u}) {
        std::vector<uint16_t> prefix(256, UINT16_C(0xfc00));
        for (unsigned token = 0; token < visible; ++token) prefix[token] = 0;
        ggml_backend_tensor_set(mask, prefix.data(), 0, 512);
        const std::vector<uint32_t> poison(1536, UINT32_C(0x7fc00001));
        ggml_backend_tensor_set(dst, poison.data(), 0, 6144);
        require(std::feclearexcept(FE_ALL_EXCEPT) == 0, "clear_host_flags");
        require(ggml_graph_compute_with_ctx(ctx, graph, 1) == GGML_STATUS_SUCCESS, "ordinary_graph_compute");
        ggml_backend_tensor_get(dst, output.data(), 0, 6144);
        float maximum = 0;
        for (unsigned i = 0; i < 1536; ++i) {
            require(std::isfinite(output[i]), "nonfinite_output");
            if (visible == 128) {
                const float delta = std::fabs(output[i] - captured[i]);
                require(std::isfinite(captured[i]) && std::isfinite(delta) &&
                        delta <= 0.004f + 0.002f * std::fabs(captured[i]), "prefix128_capture_tolerance");
                if (delta > maximum) maximum = delta;
            }
        }
        for (unsigned i = 0; i < 3; ++i)
            require(!std::memcmp(inputs[i]->data, originals[i].data(), originals[i].size()), "operand_changed");
        require(!std::memcmp(mask->data, prefix.data(), 512), "active_mask_changed");
        const std::string path = output_directory + "/" + kind + "-v" + std::to_string(visible) + ".bin";
        FILE * file = std::fopen(path.c_str(), "wbx");
        require(file != nullptr, "fresh_output_open");
        require(std::fwrite(output.data(), 1, 6144, file) == 6144, "output_write");
        require(std::fclose(file) == 0, "output_close");
        std::printf("TAIL_GOLD_OUTPUT kind=%s visible=%u outputs=1536 bytes=6144 baseline=%u max_abs=%.9g inputs_unchanged=1\n",
                    kind.c_str(), visible, unsigned(visible == 128), static_cast<double>(maximum));
    }
    ggml_backend_tensor_set(mask, originals[3].data(), 0, originals[3].size());
    require(!std::memcmp(mask->data, originals[3].data(), originals[3].size()), "mask_restore");
    std::printf("TAIL_GOLD_PASS kind=%s graphs=3 outputs_per_graph=1536 reference=archived_host_ggml\n", kind.c_str());
    ggml_backend_buffer_free(buffer);
    ggml_free(ctx);
    return 0;
}
