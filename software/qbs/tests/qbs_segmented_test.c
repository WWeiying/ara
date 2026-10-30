#include "qbs/qbs.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "CHECK %s:%d: %s\n", __FILE__, __LINE__, #x); return 1; \
} } while (0)

typedef struct {
  const qbs_plan_t *plan;
  unsigned input, column, block, calls;
  size_t activation_bytes;
} observer_t;

static unsigned char pattern(unsigned row, unsigned block, unsigned byte) {
  return (unsigned char)(row * 37u + block * 13u + byte * 7u + (block >> 8));
}

/* Interpret each descriptor as the hardware does, independently of the
   software packer's global indexing. Validate every byte, including padding. */
static qbs_status_t inspect_command(void *opaque,
    const qbs_descriptor_t *descriptor, unsigned m, const void *activations,
    float *output, size_t output_stride, unsigned n, int segmented) {
  observer_t *o = opaque;
  const qbs_plan_t *p = o->plan;
  const qbs_descriptor_fields_t f = qbs_unpack_descriptor_header(descriptor->header);
  unsigned expected_m = p->problem.m - o->input;
  if (expected_m > 4) expected_m = 4;
  unsigned expected_n = p->problem.n - o->column;
  if (expected_n > p->command_n) expected_n = p->command_n;
  unsigned expected_k = p->k_blocks - o->block;
  if (expected_k > p->command_k_blocks) expected_k = p->command_k_blocks;
  const unsigned wb = qbs_weight_block_bytes(p->problem.weight_profile);
  const unsigned ab = qbs_activation_block_bytes(p->problem.activation_profile);
  if (m != expected_m || n != expected_n || f.n != n ||
      f.k_blocks != expected_k || f.descriptor_version != QBS_DESCRIPTOR_VERSION ||
      f.weight_layout != QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR ||
      f.weight_profile != p->problem.weight_profile ||
      f.activation_profile != p->problem.activation_profile ||
      f.activation_access != QBS_ACTIVATION_ACCESS_DIRECT ||
      segmented != p->split_k || ((uintptr_t)activations & 3u) ||
      (descriptor->weight_base & 1u)) return QBS_STATUS_EXECUTION;
  const unsigned char *w = (const void *)(uintptr_t)descriptor->weight_base;
  const unsigned char *a = activations;
  const unsigned padded_n = (n + 3u) & ~3u;
  for (unsigned group = 0; group < padded_n; group += 4) {
    for (unsigned k = 0; k < expected_k; ++k) {
      for (unsigned lane = 0; lane < 4; ++lane) {
        const unsigned col = group + lane;
        for (unsigned b = 0; b < wb; ++b) {
          const unsigned global_col = p->weight_row_start + o->column + col;
          const unsigned storage_rows = p->weight_storage_rows
              ? p->weight_storage_rows : p->problem.n;
          const unsigned char expected = global_col < storage_rows
              ? pattern(global_col, o->block + k, b) : 0;
          if (*w++ != expected) return QBS_STATUS_EXECUTION;
        }
      }
    }
  }
  const int m4 = p->problem.activation_storage == QBS_ACTIVATION_STORAGE_M4_GROUPED && m == 4;
  if (f.activation_layout != (m4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
                                : QBS_ACTIVATION_LAYOUT_ROW_MAJOR))
    return QBS_STATUS_EXECUTION;
  for (unsigned row = 0; row < m; ++row) {
    for (unsigned k = 0; k < expected_k; ++k) {
      const unsigned scale = qbs_activation_scale_bytes(p->problem.activation_profile);
      const unsigned quant = qbs_activation_quant_bytes(p->problem.activation_profile);
      const unsigned aux = qbs_activation_aux_element_bytes(p->problem.activation_profile);
      for (unsigned b = 0; b < ab; ++b) {
        size_t offset = ((size_t)row * expected_k + k) * ab + b;
        if (m4) {
          offset = (size_t)k * 4 * ab;
          if (b < scale) offset += row * scale + b;
          else if (b < scale + quant) offset += 4 * scale + (b - scale) * 4 + row;
          else offset += 4 * (scale + quant) +
              ((b - scale - quant) / aux * 4 + row) * aux + (b - scale - quant) % aux;
        }
        if (a[offset] != pattern(o->input + row + 19, o->block + k, b))
          return QBS_STATUS_EXECUTION;
      }
    }
    for (unsigned col = 0; col < n; ++col)
      output[row * output_stride + col] =
          (float)((o->input + row + 1) * 64 + o->column + col + o->block);
  }
  o->activation_bytes += (size_t)m * expected_k * ab;
  ++o->calls;
  o->column += n;
  if (o->column == p->problem.n) {
    o->column = 0;
    o->block += expected_k;
    if (o->block == p->k_blocks) { o->block = 0; o->input += m; }
  }
  return QBS_STATUS_OK;
}

static int run_view(unsigned profile, unsigned m, unsigned n, unsigned k,
                    unsigned segment, unsigned storage,
                    unsigned storage_rows, unsigned row_start, int view) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  const unsigned act = qbs_default_activation_profile(profile);
  const unsigned wb = qbs_weight_block_bytes(profile);
  const unsigned ab = qbs_activation_block_bytes(act);
  const qbs_problem_t problem = {
      .weight_profile = profile, .activation_profile = act,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = storage, .m = m, .n = n,
      .k_elements = k * qbs_weight_block_elements(profile),
  };
  qbs_plan_t plan;
  if (view)
    CHECK(qbs_plan_create_segmented_r4_view(&device, &problem, segment,
        storage_rows, row_start, &plan) == QBS_STATUS_OK);
  else
    CHECK(qbs_plan_create_segmented_r4(&device, &problem, segment, &plan) == QBS_STATUS_OK);
  CHECK(plan.weight_storage_rows == storage_rows && plan.weight_row_start == row_start);
  CHECK(plan.command_n == 32 && plan.command_k_blocks == segment);
  const size_t source_bytes = (size_t)storage_rows * k * wb;
  const size_t packed_bytes = qbs_weight_storage_bytes(profile, problem.weight_layout, storage_rows, k);
  const size_t act_bytes = (size_t)m * k * ab;
  unsigned char *source = malloc(source_bytes);
  unsigned char *weights = malloc(packed_bytes);
  unsigned char *activation = malloc(act_bytes);
  unsigned char *packed_act = malloc(act_bytes);
  void *workspace = malloc(plan.workspace_bytes ? plan.workspace_bytes : 1);
  const size_t stride = n + 3;
  float *output = malloc(m * stride * sizeof(float));
  CHECK(source && weights && activation && packed_act && workspace && output);
  for (unsigned row = 0; row < storage_rows; ++row)
    for (unsigned block = 0; block < k; ++block)
      for (unsigned b = 0; b < wb; ++b)
        source[((size_t)row * k + block) * wb + b] = pattern(row, block, b);
  for (unsigned row = 0; row < m; ++row)
    for (unsigned block = 0; block < k; ++block)
      for (unsigned b = 0; b < ab; ++b)
        activation[((size_t)row * k + block) * ab + b] = pattern(row + 19, block, b);
  memcpy(packed_act, activation, act_bytes);
  if (storage == QBS_ACTIVATION_STORAGE_M4_GROUPED)
    for (unsigned row = 0; row + 4 <= m; row += 4)
      CHECK(qbs_pack_activation_m4(act, activation + (size_t)row * k * ab,
          (size_t)4 * k * ab, k, packed_act + (size_t)row * k * ab,
          (size_t)4 * k * ab) == QBS_STATUS_OK);
  CHECK(qbs_repack_weight_r4_segmented(profile, source, source_bytes, storage_rows, k,
      segment, weights, packed_bytes) == QBS_STATUS_OK);
  CHECK(qbs_repack_weight_r4_segmented(profile, source, source_bytes - 1, storage_rows, k,
      segment, weights, packed_bytes) == QBS_STATUS_BUFFER_TOO_SMALL);
  for (size_t i = 0; i < m * stride; ++i) output[i] = -123;
  observer_t observed = {.plan = &plan};
  CHECK(qbs_execute(&plan, weights, packed_bytes - 1, packed_act, act_bytes,
      output, m * stride, stride, workspace, plan.workspace_bytes,
      inspect_command, &observed) == QBS_STATUS_BUFFER_TOO_SMALL);
  CHECK(observed.calls == 0);
  for (size_t i = 0; i < m * stride; ++i) CHECK(output[i] == -123);
  CHECK(qbs_execute(&plan, weights, packed_bytes, packed_act, act_bytes,
      output, m * stride, stride, workspace, plan.workspace_bytes,
      inspect_command, &observed) == QBS_STATUS_OK);
  CHECK(observed.input == m && observed.column == 0 && observed.block == 0);
  CHECK(observed.calls == ((m + 3) / 4) * ((n + 31) / 32) * ((k + segment - 1) / segment));
  for (unsigned row = 0; row < m; ++row) {
    for (unsigned col = 0; col < stride; ++col) {
      float expected = col < n ? 0 : -123;
      if (col < n)
        for (unsigned start = 0; start < k; start += segment)
          expected += (float)((row + 1) * 64 + col + start);
      CHECK(output[row * stride + col] == expected);
    }
  }
  if (!view && profile == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT && m == 4 && n == 32 && k == 280 &&
      storage == QBS_ACTIVATION_STORAGE_ROW_MAJOR) {
    printf("Q8_0 M4/N32/K8960: segmented commands=%u activation_bytes=%zu\n",
           observed.calls, observed.activation_bytes);
    qbs_plan_t old;
    CHECK(qbs_plan_create(&device, &problem, &old) == QBS_STATUS_OK);
    CHECK(qbs_repack_weight_r4(profile, source, source_bytes, n, k,
                              weights, packed_bytes) == QBS_STATUS_OK);
    free(workspace);
    workspace = malloc(old.workspace_bytes);
    CHECK(workspace);
    observer_t original = {.plan = &old};
    CHECK(qbs_execute(&old, weights, packed_bytes, packed_act, act_bytes,
        output, m * stride, stride, workspace, old.workspace_bytes,
        inspect_command, &original) == QBS_STATUS_OK);
    CHECK(original.calls == observed.calls * 8);
    CHECK(original.activation_bytes == observed.activation_bytes * 8);
    printf("Q8_0 M4/N32/K8960: original commands=%u activation_bytes=%zu\n",
           original.calls, original.activation_bytes);
  }
  free(output); free(workspace); free(packed_act); free(activation); free(weights); free(source);
  return 0;
}

static int run_shape(unsigned profile, unsigned m, unsigned n, unsigned k,
                     unsigned segment, unsigned storage) {
  return run_view(profile, m, n, k, segment, storage, n, 0, 0);
}

static int invalid_contracts(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  qbs_problem_t p = {.weight_profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 1, .n = 33, .k_elements = 8960};
  qbs_plan_t plan;
  CHECK(qbs_plan_create_segmented_r4_view(NULL, &p, 256, 37, 4, &plan) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_plan_create_segmented_r4_view(&device, NULL, 256, 37, 4, &plan) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_plan_create_segmented_r4_view(&device, &p, 256, 37, 4, NULL) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_plan_create_segmented_r4_view(&device, &p, 256, 0, 0, &plan) == QBS_STATUS_SHAPE);
  CHECK(qbs_plan_create_segmented_r4_view(&device, &p, 256, 37, 2, &plan) == QBS_STATUS_SHAPE);
  CHECK(qbs_plan_create_segmented_r4_view(&device, &p, 256, 37, 8, &plan) == QBS_STATUS_SHAPE);
  CHECK(qbs_plan_create_segmented_r4_view(&device, &p, 256, 37, 40, &plan) == QBS_STATUS_SHAPE);
  CHECK(qbs_plan_create_segmented_r4_view(&device, &p, 256, UINT32_MAX,
      UINT32_MAX - 3, &plan) == QBS_STATUS_SHAPE);
  CHECK(qbs_plan_create_segmented_r4(&device, &p, 0, &plan) != QBS_STATUS_OK);
  CHECK(qbs_plan_create_segmented_r4(&device, &p, 257, &plan) != QBS_STATUS_OK);
  device.capabilities.max_k_blocks = 16;
  CHECK(qbs_plan_create_segmented_r4(&device, &p, 256, &plan) != QBS_STATUS_OK);
  CHECK(qbs_plan_create_segmented_r4(&device, &p, 16, &plan) == QBS_STATUS_OK);
  p.weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
  CHECK(qbs_plan_create_segmented_r4(&device, &p, 16, &plan) == QBS_STATUS_LAYOUT);
  p.weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
  p.activation_storage = QBS_ACTIVATION_STORAGE_M8_GROUPED;
  p.m = 8;
  CHECK(qbs_plan_create_segmented_r4(&device, &p, 16, &plan) == QBS_STATUS_SHAPE);
  return 0;
}

int main(void) {
  const unsigned profiles[] = {QBS_WEIGHT_PROFILE_Q2_K, QBS_WEIGHT_PROFILE_Q3_K,
      QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q5_K, QBS_WEIGHT_PROFILE_Q6_K,
      QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q5_0,
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT, QBS_WEIGHT_PROFILE_IQ4_NL};
  const unsigned rows[] = {1, 4, 5, 31, 32, 33};
  const unsigned blocks[] = {1, 3, 255, 256, 257, 280, 513};
  const unsigned inputs[] = {1, 3, 4, 5};
  unsigned count = 0;
  unsigned views = 0;
  CHECK(invalid_contracts() == 0);
  for (unsigned p = 0; p < sizeof(profiles) / sizeof(profiles[0]); ++p) {
    for (unsigned n = 0; n < sizeof(rows) / sizeof(rows[0]); ++n)
      for (unsigned k = 0; k < sizeof(blocks) / sizeof(blocks[0]); ++k)
        for (unsigned m = 0; m < sizeof(inputs) / sizeof(inputs[0]); ++m) {
          CHECK(run_shape(profiles[p], inputs[m], rows[n], blocks[k], 256,
                          QBS_ACTIVATION_STORAGE_ROW_MAJOR) == 0);
          ++count;
        }
    CHECK(run_shape(profiles[p], 5, 33, 17, 3, QBS_ACTIVATION_STORAGE_ROW_MAJOR) == 0);
    CHECK(run_shape(profiles[p], 5, 33, 257, 256, QBS_ACTIVATION_STORAGE_M4_GROUPED) == 0);
    count += 2;
    const unsigned starts[] = {0, 4, 8, 32, 36};
    const unsigned lengths[] = {4, 4, 27, 5, 1};
    const unsigned view_blocks[] = {1, 17, 257, 280, 513};
    for (unsigned v = 0; v < sizeof(starts) / sizeof(starts[0]); ++v)
      for (unsigned k = 0; k < sizeof(view_blocks) / sizeof(view_blocks[0]); ++k)
        for (unsigned m = 0; m < sizeof(inputs) / sizeof(inputs[0]); ++m)
          for (unsigned grouped = 0; grouped < 2; ++grouped) {
            CHECK(run_view(profiles[p], inputs[m], lengths[v], view_blocks[k],
                k == 1 ? 3 : 256, grouped ? QBS_ACTIVATION_STORAGE_M4_GROUPED
                                         : QBS_ACTIVATION_STORAGE_ROW_MAJOR,
                37, starts[v], 1) == 0);
            ++views;
          }
    /* A row view spanning two hardware N tiles, with a nonzero R4 offset. */
    CHECK(run_view(profiles[p], 5, 65, 257, 256,
        QBS_ACTIVATION_STORAGE_M4_GROUPED, 73, 4, 1) == 0);
    ++views;
  }
  printf("QBS segmented R4 byte addressing and execution: %u shapes PASS\n", count);
  printf("QBS segmented R4 full-storage views: %u shapes PASS\n", views);
  return 0;
}
