#include "../../qbs/qbs_ref.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { K = 2048, N = 128, M = 4, KB = 8 };

static void need(int condition, const char *reason) {
    if (!condition) { fprintf(stderr, "PROJECTION_GOLDEN_FAIL %s\n", reason); exit(1); }
}
static void *load(const char *dir, const char *name, size_t bytes) {
    char path[4096]; need(snprintf(path, sizeof(path), "%s/%s", dir, name) < (int)sizeof(path), "path");
    FILE *f = fopen(path, "rb"); need(f != NULL, "open_input");
    void *data = malloc(bytes); need(data != NULL, "allocate");
    need(fread(data, 1, bytes, f) == bytes && fgetc(f) == EOF && !ferror(f), "input_size");
    need(fclose(f) == 0, "close_input"); return data;
}
static void save(const char *dir, const char *name, const void *data, size_t bytes) {
    char path[4096]; need(snprintf(path, sizeof(path), "%s/%s", dir, name) < (int)sizeof(path), "path");
    FILE *f = fopen(path, "wb"); need(f != NULL, "open_output");
    need(fwrite(data, 1, bytes, f) == bytes && fclose(f) == 0, "write");
}
int main(int argc, char **argv) {
    need(argc == 3, "arguments");
    const float *input = load(argv[1], "activation_f32.bin", M*K*sizeof(float));
    qbs_block_q8_k_t activation[M*KB]; qbs_block_q8_kx4_t grouped[KB];
    need(qbs_ref_quantize_q8_k(input, M*K, activation, M*KB) == QBS_REF_OK, "quantize");
    need(qbs_ref_pack_activation_m4(activation, M*KB, KB, grouped, KB) == QBS_REF_OK, "pack");
    save(argv[2], "activation_q8k_m4.bin", grouped, sizeof(grouped));
    const unsigned profiles[] = {QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q6_K};
    const char *names[] = {"attn_q", "attn_k", "attn_v"};
    for (unsigned part = 0; part < 3; ++part) {
        char name[64]; snprintf(name, sizeof(name), "%s.bin", names[part]);
        const size_t row_bytes = KB*qbs_weight_block_bytes(profiles[part]);
        const size_t bytes = N*row_bytes;
        const unsigned char *weights = load(argv[1], name, bytes);
        unsigned char *packed = malloc(bytes); need(packed != NULL, "allocate_weight");
        need(qbs_ref_repack_weight_r4(profiles[part], weights, bytes, N, KB, packed, bytes) == QBS_REF_OK,
             "weight_repack");
        float output[M*N]; unsigned flags = 0;
        for (unsigned start = 0; start < N; start += QBS_MAX_N) {
            qbs_descriptor_fields_t fields = {.descriptor_version=QBS_DESCRIPTOR_VERSION,
                .weight_profile=profiles[part], .activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
                .weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                .activation_layout=QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, .n=QBS_MAX_N, .k_blocks=KB};
            qbs_descriptor_t descriptor = {.header=qbs_pack_descriptor_header(&fields), .weight_base=0x1000};
            float row_major[M*QBS_MAX_N], r4[M*QBS_MAX_N]; qbs_ref_result_t result = {0};
            need(qbs_ref_execute(&descriptor, M, 4, 1024, 0x2000, packed+start*row_bytes,
                QBS_MAX_N*row_bytes, grouped, sizeof(grouped), r4, M*QBS_MAX_N, NULL, NULL, &result) == QBS_REF_OK,
                "r4_reference");
            flags |= result.fflags;
            fields.weight_layout=QBS_WEIGHT_LAYOUT_ROW_MAJOR; descriptor.header=qbs_pack_descriptor_header(&fields);
            need(qbs_ref_execute(&descriptor, M, 4, 1024, 0x2000, weights+start*row_bytes,
                QBS_MAX_N*row_bytes, grouped, sizeof(grouped), row_major, M*QBS_MAX_N, NULL, NULL, &result) == QBS_REF_OK &&
                !memcmp(row_major, r4, sizeof(r4)), "row_major_r4_disagree");
            for (unsigned row = 0; row < M; ++row)
                memcpy(output+row*N+start, r4+row*QBS_MAX_N, QBS_MAX_N*sizeof(float));
        }
        snprintf(name, sizeof(name), "%s_r4.bin", names[part]); save(argv[2], name, packed, bytes);
        snprintf(name, sizeof(name), "%s_expected.bin", names[part]); save(argv[2], name, output, sizeof(output));
        snprintf(name, sizeof(name), "%s_fflags.bin", names[part]); save(argv[2], name, &flags, sizeof(flags));
        printf("PROJECTION_GOLDEN part=%u profile=%u m=4 n=128 k=2048 flags=%u\n", part, profiles[part], flags);
        free(packed); free((void *)weights);
    }
    free((void *)input); puts("PROJECTION_GOLDEN_PASS row_major_r4_equal=1"); return 0;
}
