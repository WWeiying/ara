#define _POSIX_C_SOURCE 200809L
#include "qbs/qbs.h"
#include "micro_kernels.h"

#include <fenv.h>
#include <inttypes.h>
#include <math.h>
#include <setjmp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { N = 32, K = 1536, KB = 6, GUARD = 64 };
_Static_assert(QBS_ARCH_VERSION == 3 && QBS_DESCRIPTOR_VERSION == 2,
               "requires arch-v3 / descriptor-v2");
_Static_assert(sizeof(qbs_descriptor_t) == 16 &&
               _Alignof(qbs_descriptor_t) == 16, "descriptor ABI");

typedef struct {
    unsigned char *base;
    void *data;
    size_t bytes;
} buffer_t;

static sigjmp_buf probe_return;
static volatile sig_atomic_t probing;
static unsigned query_calls, native_calls;

static void fail(const char *what) {
    fprintf(stderr, "[QBS] FAIL %s\n", what);
    exit(1);
}

static void require(int condition, const char *what) {
    if (!condition) fail(what);
}

static buffer_t allocate(size_t bytes) {
    void *base = NULL;
    require(posix_memalign(&base, GUARD, bytes + 2 * GUARD) == 0, "allocation");
    memset(base, 0xa5, bytes + 2 * GUARD);
    return (buffer_t){base, (unsigned char *)base + GUARD, bytes};
}

static void guards(const buffer_t *b) {
    for (size_t i = 0; i < GUARD; ++i)
        require(b->base[i] == 0xa5 &&
                b->base[GUARD + b->bytes + i] == 0xa5, "buffer guard");
}

static void load(const char *name, buffer_t *b) {
    char path[160];
    require(snprintf(path, sizeof(path), "/qbs/%s", name) < (int)sizeof(path),
            "path");
    FILE *f = fopen(path, "rb");
    require(f != NULL, "open input");
    require(fread(b->data, 1, b->bytes, f) == b->bytes && fgetc(f) == EOF,
            "input size");
    require(fclose(f) == 0, "close input");
}

static void unchanged(const char *name, const buffer_t *b) {
    buffer_t copy = allocate(b->bytes);
    load(name, &copy);
    require(memcmp(b->data, copy.data, b->bytes) == 0, "input changed");
    free(copy.base);
}

static void illegal(int signal_number) {
    (void)signal_number;
    if (probing) siglongjmp(probe_return, 1);
    _Exit(1);
}

static uint64_t read_info(void *context, unsigned index) {
    (void)context;
    /* Only user-accessible vector state; no mstatus/SBI/MMIO app API. */
    __asm__ volatile("vsetvli zero, zero, e32, m1, ta, ma\n"
                     "csrw vstart, zero" : : : "memory");
    ++query_calls;
    uint64_t word = qbs_native_info(NULL, index);
    printf("[QBS] INFO index=%u word=0x%016" PRIx64 "\n", index, word);
    return word;
}

static qbs_status_t probe(qbs_device_t *device, int *trapped) {
    struct sigaction old, action = {.sa_handler = illegal};
    require(sigemptyset(&action.sa_mask) == 0 &&
            sigaction(SIGILL, &action, &old) == 0, "probe signal setup");
    qbs_status_t status;
    if (sigsetjmp(probe_return, 1) == 0) {
        probing = 1;
        status = qbs_device_query(read_info, NULL, device);
    } else {
        *trapped = 1;
        status = QBS_STATUS_RUNTIME_UNAVAILABLE;
    }
    probing = 0;
    require(sigaction(SIGILL, &old, NULL) == 0, "probe signal restore");
    return status;
}

static qbs_status_t native(void *context, const qbs_descriptor_t *descriptor,
                           unsigned m, const void *activation, float *output,
                           size_t stride, unsigned n, int segmented) {
    (void)context;
    qbs_descriptor_fields_t fields = qbs_unpack_descriptor_header(descriptor->header);
    require(((uintptr_t)descriptor & 15) == 0 &&
            fields.activation_access == QBS_ACTIVATION_ACCESS_DIRECT &&
            fields.context_id == 0 && fields.context_generation == 0 &&
            fields.n == N && fields.k_blocks == KB && m == 1 && n == N &&
            !segmented, "DIRECT descriptor");
    printf("[QBS] EXEC descriptor_va=%p weight_va=0x%" PRIx64
           " activation_va=%p output_va=%p header=0x%016" PRIx64 "\n",
           (const void *)descriptor, descriptor->weight_base, activation,
           (void *)output, descriptor->header);
    ++native_calls;
    qbs_status_t status = qbs_native_execute_command(
        NULL, descriptor, m, activation, output, stride, n, segmented);
    require(status == QBS_STATUS_OK, "native returned failure; no retry");
    puts("[QBS] NATIVE_RETURN status=ok");
    return status;
}

static void compare(const char *name, const float *actual, const float *golden) {
    float max_abs = 0;
    unsigned mismatches = 0;
    for (unsigned i = 0; i < N; ++i) {
        float difference = fabsf(actual[i] - golden[i]);
        if (!isfinite(actual[i]) || !isfinite(golden[i]) ||
            difference > 0.002f + 0.002f * fabsf(golden[i])) ++mismatches;
        if (difference > max_abs) max_abs = difference;
        if (strcmp(name, "native_frozen") == 0) {
            uint32_t bits;
            memcpy(&bits, actual + i, sizeof(bits));
            printf("[QBS] OUTPUT index=%u bits=%08" PRIx32 " golden=%.9g\n",
                   i, bits, golden[i]);
        }
    }
    printf("[QBS] COMPARE %s mismatches=%u/32 max_abs=%.9g atol=0.002 rtol=0.002\n",
           name, mismatches, max_abs);
    require(mismatches == 0, "numerical mismatch");
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    puts("OS_CUSTOM_CONTEXT=NOT_VALIDATED");
    puts("AKV_NATIVE_COMPUTE=UNAVAILABLE");
    require(argc == 2, "mode required");
    int disabled = strcmp(argv[1], "--disable-qbs") == 0;
    int required = strcmp(argv[1], "--require-qbs") == 0;
    require(disabled || required || strcmp(argv[1], "--auto") == 0, "mode");
    require(fesetround(FE_TONEAREST) == 0, "RNE");

    qbs_device_t device;
    int trapped = 0;
    qbs_status_t capability = disabled ? QBS_STATUS_RUNTIME_UNAVAILABLE :
                                        probe(&device, &trapped);
    if (disabled) puts("[QBS] CAPABILITY disabled");
    else if (trapped) puts("[QBS] CAPABILITY unavailable signal=SIGILL");
    else printf("[QBS] CAPABILITY %s\n", qbs_status_string(capability));
    if (required && capability != QBS_STATUS_OK) {
        puts("QBS_NATIVE_COMPUTE=UNSUPPORTED");
        printf("[QBS] COUNTS query_calls=%u native_calls=0\n", query_calls);
        return 77;
    }

    buffer_t weight = allocate(N * KB * sizeof(block_q4_K));
    buffer_t activation = allocate(K * sizeof(float));
    buffer_t quant = allocate(KB * sizeof(block_q8_K));
    buffer_t frozen_quant = allocate(quant.bytes);
    buffer_t golden = allocate(N * sizeof(float));
    buffer_t rvv = allocate(N * sizeof(float));
    buffer_t output = allocate(N * sizeof(float));
    buffer_t packed = allocate(weight.bytes);
    load("weight.bin", &weight);
    load("activation.bin", &activation);
    load("golden.bin", &golden);
    load("activation_q8.bin", &frozen_quant);
    q4km_quantize_row_q8_K(activation.data, quant.data, K);
    require(memcmp(quant.data, frozen_quant.data, quant.bytes) == 0,
            "independent frozen Q8 quantization");
    puts("[QBS] QUANTIZATION byte_exact=1752");
    for (unsigned row = 0; row < N; ++row)
        ((float *)rvv.data)[row] = q4km_vec_dot_q4_K_q8_K(
            (block_q4_K *)weight.data + row * KB, quant.data, K);
    compare("rvv_frozen", rvv.data, golden.data);

    if (capability == QBS_STATUS_OK) {
        require(qbs_device_supports_profile(&device, QBS_WEIGHT_PROFILE_Q4_K,
                                           QBS_ACTIVATION_PROFILE_Q8_K), "profile");
        printf("[QBS] ABI arch=%u desc=%u numerical=%u max_n=%u\n",
               device.capabilities.architecture_version,
               device.capabilities.descriptor_version,
               device.capabilities.numerical_contract_version,
               device.capabilities.max_n);
        qbs_problem_t problem = {
            .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
            .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
            .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
            .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
            .m = 1, .n = N, .k_elements = K,
        };
        qbs_plan_t plan;
        require(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK &&
                plan.k_blocks == KB && plan.workspace_bytes == 0 &&
                !plan.split_k, "single tile plan");
        /* Plan command sizes are limits; the cursor yields the clipped tile. */
        qbs_plan_cursor_t cursor;
        qbs_command_t command;
        int has_command;
        qbs_plan_cursor_reset(&cursor);
        require(qbs_plan_next(&plan, &cursor, &command, &has_command) == QBS_STATUS_OK &&
                has_command && command.m == 1 && command.n == N &&
                command.k_blocks == KB && command.input_start == 0 &&
                command.output_start == 0 && command.k_block_start == 0 &&
                !command.accumulate && !command.gather_activation, "emitted tile");
        require(qbs_plan_next(&plan, &cursor, &command, &has_command) == QBS_STATUS_OK &&
                !has_command, "exactly one tile");
        puts("[QBS] PLAN emitted_commands=1 M=1 N=32 K_blocks=6 DIRECT");
        require(qbs_repack_weight_r4(QBS_WEIGHT_PROFILE_Q4_K, weight.data,
                weight.bytes, N, KB, packed.data, packed.bytes) == QBS_STATUS_OK,
                "shared repack");
        unsigned char packed_copy[N * KB * sizeof(block_q4_K)];
        memcpy(packed_copy, packed.data, packed.bytes);
        for (unsigned i = 0; i < N; ++i) ((float *)output.data)[i] = NAN;
        unsigned char sentinel[N * sizeof(float)];
        memcpy(sentinel, output.data, output.bytes);
        require(qbs_execute(&plan, packed.data, packed.bytes, quant.data,
                quant.bytes, output.data, N - 1, N, NULL, 0, native, NULL) ==
                QBS_STATUS_BUFFER_TOO_SMALL, "capacity rejection");
        require(qbs_execute(&plan, packed.data, packed.bytes,
                (unsigned char *)quant.data + 1, quant.bytes, output.data,
                N, N, NULL, 0, native, NULL) == QBS_STATUS_BUFFER_ALIGNMENT,
                "alignment rejection");
        require(native_calls == 0 && memcmp(sentinel, output.data, output.bytes) == 0,
                "rejection wrote output or entered native");
        puts("[QBS] PRECHECK capacity_alignment_rejected native_calls=0 unchanged=1");
        require(qbs_execute(&plan, packed.data, packed.bytes, quant.data,
                quant.bytes, output.data, N, N, NULL, 0, native, NULL) ==
                QBS_STATUS_OK && native_calls == 1, "one native command");
        require(memcmp(packed_copy, packed.data, packed.bytes) == 0,
                "packed input changed");
        compare("native_frozen", output.data, golden.data);
        compare("native_rvv", output.data, rvv.data);
    }
    unchanged("weight.bin", &weight);
    unchanged("activation.bin", &activation);
    unchanged("golden.bin", &golden);
    unchanged("activation_q8.bin", &quant);
    unchanged("activation_q8.bin", &frozen_quant);
    buffer_t *buffers[] = {&weight, &activation, &quant, &frozen_quant,
                           &golden, &rvv, &output, &packed};
    for (size_t i = 0; i < sizeof(buffers) / sizeof(buffers[0]); ++i) {
        guards(buffers[i]);
        free(buffers[i]->base);
    }
    puts("[QBS] GUARDS inputs_unchanged=1 guards=8/8");
    printf("[QBS] COUNTS query_calls=%u native_calls=%u\n", query_calls, native_calls);
    if (capability == QBS_STATUS_OK) puts("QBS_NATIVE_COMPUTE=PASS");
    else {
        puts("QBS_NATIVE_COMPUTE=NOT_RUN");
        puts("RVV_FALLBACK=PASS");
    }
    return 0;
}
