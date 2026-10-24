/* Reuse the sealed unit fixture and its independent QBS arithmetic model. */
#define main contiguous_fixture_main
#include "test_native.c"
#undef main
#include "software/akv/experimental/quantized_kv/runtime_strided.h"
#include <stdlib.h>

static unsigned char interleaved_keys[sizeof(keys)] __attribute__((aligned(64)));
static unsigned char interleaved_values[sizeof(values)] __attribute__((aligned(64)));
static float expected[16][136];
static float max_query[12][256], max_output[12][256], max_expected[12][256];
static unsigned char max_key[2 * 65 * 272] __attribute__((aligned(64)));
static unsigned char max_interleaved[sizeof(max_key)] __attribute__((aligned(64)));
static unsigned char max_value[sizeof(max_key)] __attribute__((aligned(64)));

static qbs_status_t execute_panel(void *opaque, const qbs_descriptor_t *descriptor,
    unsigned m, const void *activation, float *out, size_t stride, unsigned n, int segmented) {
  executor_t *e = opaque;
  ++e->calls;
  if (e->fail_at && e->calls == e->fail_at) return QBS_STATUS_EXECUTION;
  const qbs_descriptor_fields_t fields = qbs_unpack_descriptor_header(descriptor->header);
  assert(!segmented && fields.n == n && m <= 4 && n <= 32 && stride >= n &&
         fields.activation_access == QBS_ACTIVATION_ACCESS_DIRECT);
  const size_t row = fields.k_blocks *
      (e->input->key_encoding == QBS_WEIGHT_ENCODING_Q4_0 ? 18u : 34u);
  float packed[128];
  qbs_ref_result_t result;
  assert(qbs_ref_execute(descriptor, m, 8, 1024, (uintptr_t)activation,
      (const void *)(uintptr_t)descriptor->weight_base, n * row,
      activation, m * fields.k_blocks * 34u, packed, 128, NULL, NULL, &result) == QBS_REF_OK);
  assert(!result.fflags);
  for (unsigned head = 0; head < m; ++head)
    memcpy(out + head * stride, packed + head * 32, n * sizeof(float));
  return QBS_STATUS_OK;
}

static void maximum_panel(void *scratch, size_t bytes) {
  akv_quant_selection_input_t p = prepare(128, 6, 2, 33, 0);
  for (unsigned h = 0; h < 12; ++h) for (unsigned d = 0; d < 256; ++d)
    max_query[h][d] = (int)((h + d) % 7) - 3;
  for (unsigned h = 0; h < 2; ++h) for (unsigned t = 0; t < 65; ++t)
    for (unsigned b = 0; b < 8; ++b) {
      unsigned char *k = max_key + (h * 65 + t) * 272 + b * 34;
      unsigned char *v = max_value + (h * 65 + t) * 272 + b * 34;
      const uint16_t one = 0x3c00;
      memcpy(k, &one, 2); memcpy(v, &one, 2);
      for (unsigned j = 0; j < 32; ++j) {
        k[2 + j] = (unsigned char)(int8_t)((int)((t + h + b + j) % 7) - 3);
        v[2 + j] = (unsigned char)(int8_t)((int)((t + h + j) % 9) - 4);
      }
    }
  p.query = (akv_quant_tensor_view_t){max_query, sizeof(max_query), 1024, 1024, 256, 1, 12};
  p.key = (akv_quant_tensor_view_t){max_key, sizeof(max_key), 272, 65 * 272, 256, 65, 2};
  p.value = (akv_quant_tensor_view_t){max_value, sizeof(max_value), 272, 65 * 272, 256, 65, 2};
  p.output = (akv_quant_tensor_view_t){max_output, sizeof(max_output), 1024, 1024, 256, 1, 12};
  executor_t executor = {.input = &p};
  akv_quant_native_bindings_t bindings = {quantize, decode, scale, mad, execute_panel, &executor};
  akv_quant_native_report_t original;
  assert(akv_quant_native_execute(&p, &bindings, &workspace, sizeof(workspace), &original) == AKV_QUANT_NATIVE_OK);
  memcpy(max_expected, max_output, sizeof(max_output));
  for (unsigned t = 0; t < 65; ++t) for (unsigned h = 0; h < 2; ++h)
    memcpy(max_interleaved + (t * 2 + h) * 272, max_key + (h * 65 + t) * 272, 272);
  p.key.data = max_interleaved; p.key.token_stride = 544; p.key.head_stride = 272;
  akv_quant_strided_report_t report;
  assert(akv_quant_strided_execute(&p, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_OK);
  assert(memcmp(max_output, max_expected, sizeof(max_output)) == 0);
  assert(report.key_panels == 4 && report.key_bytes == 2 * 33 * 272);
}

static void repeated_single_panel(void *scratch, size_t bytes) {
  akv_quant_selection_input_t normalized = prepare(128, 6, 1, 2, 0);
  akv_quant_selection_input_t padded = normalized;
  padded.key.data = interleaved_keys;
  padded.key.token_stride = 138;
  padded.key.head_stride = 65 * 138;
  memset(interleaved_keys, 0xa5, sizeof(interleaved_keys));
  for (unsigned token = 0; token < 65; ++token)
    memcpy(interleaved_keys + token * 138, keys + token * 136, 136);
  executor_t executor = {.input = &padded};
  akv_quant_native_bindings_t bindings = {quantize, decode, scale, mad, execute_panel, &executor};
  akv_quant_strided_report_t report;
  assert(akv_quant_strided_execute(&padded, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_OK);
  memcpy(expected, output, sizeof(output));
  /* Same head, same tile and same count on the next call: only the explicit
   * invocation invalidation prevents the old panel from matching. */
  interleaved_keys[2] ^= 63;
  keys[2] ^= 63;
  assert(akv_quant_strided_execute(&padded, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_OK);
  assert(report.key_panels == 1 && report.key_bytes == 2 * 136);
  assert(memcmp(output, expected, sizeof(output)) != 0);
  memcpy(expected, output, sizeof(output));
  executor.input = &normalized;
  akv_quant_native_report_t original;
  assert(akv_quant_native_execute(&normalized, &bindings, &workspace, sizeof(workspace),
                                 &original) == AKV_QUANT_NATIVE_OK);
  assert(memcmp(output, expected, sizeof(output)) == 0);
}

int main(void) {
  assert(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  const size_t bytes = akv_quant_strided_workspace_bytes();
  void *scratch = aligned_alloc(64, bytes);
  assert(scratch && !(bytes % 64));
  const unsigned dims[] = {32, 96, 128}, groups[] = {1, 3, 6, 7};
  const unsigned visible[] = {1, 31, 32, 33, 64, 65};
  unsigned cases = 0;
  for (unsigned d = 0; d < 3; ++d) for (unsigned g = 0; g < 4; ++g)
    for (unsigned kv = 1; kv <= 2; ++kv) for (unsigned t = 0; t < 6; ++t)
      for (unsigned q4 = 0; q4 < 2; ++q4) {
        akv_quant_selection_input_t p = prepare(dims[d], groups[g], kv, visible[t], q4);
        executor_t executor = {.input = &p};
        akv_quant_native_bindings_t bindings = {quantize, decode, scale, mad, execute, &executor};
        akv_quant_native_report_t contiguous;
        assert(akv_quant_native_execute(&p, &bindings, &workspace, sizeof(workspace),
                                       &contiguous) == AKV_QUANT_NATIVE_OK);
        memcpy(expected, output, sizeof(expected));
        akv_quant_strided_report_t report;
        bindings.execute = execute_panel;
        executor.calls = 0;
        assert(akv_quant_strided_execute(&p, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_OK);
        assert(!report.key_panels && !report.key_bytes && memcmp(output, expected, sizeof(output)) == 0);
        akv_quant_selection_input_t normalized = p;
        const size_t row = p.key.token_stride, vrow = p.value.token_stride;
        for (unsigned token = 0; token < 65; ++token) for (unsigned h = 0; h < kv; ++h) {
          memcpy(interleaved_keys + (token * kv + h) * row, keys + (h * 65 + token) * row, row);
          memcpy(interleaved_values + (token * kv + h) * vrow, values + (h * 65 + token) * vrow, vrow);
        }
        p.key.data = interleaved_keys; p.key.token_stride = kv * row; p.key.head_stride = row;
        p.value.data = interleaved_values; p.value.token_stride = kv * vrow; p.value.head_stride = vrow;
        executor.calls = quant_calls = decode_calls = 0;
        assert(akv_quant_strided_execute(&p, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_OK);
        assert(memcmp(output, expected, sizeof(output)) == 0);
        assert(report.native.command_attempts == contiguous.command_attempts &&
               report.native.completed_groups == kv && report.native.value_decodes == kv * visible[t]);
        assert(quant_calls == kv * groups[g] && decode_calls == kv * visible[t]);
        assert(report.key_panels == (kv == 1 ? 0 : kv * ((visible[t] + 31) / 32)));
        assert(report.key_bytes == (kv == 1 ? 0 : kv * visible[t] * row));
        /* Reuse one scratch area with changed inputs: cached panels must not survive a call. */
        interleaved_keys[2] ^= 1;
        assert(akv_quant_strided_execute(&p, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_OK);
        memcpy(expected, output, sizeof(output));
        keys[2] ^= 1;
        executor.input = &normalized;
        assert(akv_quant_native_execute(&normalized, &bindings, &workspace, sizeof(workspace),
                                       &contiguous) == AKV_QUANT_NATIVE_OK);
        assert(memcmp(output, expected, sizeof(output)) == 0);
        keys[2] ^= 1;
        interleaved_keys[2] ^= 1;
        ++cases;
      }
  repeated_single_panel(scratch, bytes);
  maximum_panel(scratch, bytes);
  akv_quant_selection_input_t p = prepare(128, 6, 2, 33, 0);
  p.key.data = interleaved_keys; p.key.token_stride = 272; p.key.head_stride = 136;
  /* Restore valid blocks after the last matrix entry. */
  for (unsigned token = 0; token < 65; ++token) for (unsigned h = 0; h < 2; ++h)
    memcpy(interleaved_keys + (token * 2 + h) * 136, keys + (h * 65 + token) * 136, 136);
  executor_t executor = {.input = &p, .fail_at = 1};
  akv_quant_native_bindings_t bindings = {quantize, decode, scale, mad, execute_panel, &executor};
  akv_quant_strided_report_t report;
  quant_calls = decode_calls = 0;
  assert(akv_quant_strided_execute(&p, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_EXECUTION_FAILED);
  assert(report.native.command_attempts == 1 && !report.native.completed_groups &&
         report.key_panels == 1 && report.key_bytes == 32 * 136 && !decode_calls);
  memset(output, 0xa5, sizeof(output));
  quant_calls = decode_calls = executor.calls = 0;
  p.key.bytes = 1;
  assert(akv_quant_strided_execute(&p, &bindings, scratch, bytes, &report) == AKV_QUANT_NATIVE_FALLBACK);
  assert(!quant_calls && !decode_calls && !executor.calls && !report.key_panels);
  for (size_t i = 0; i < sizeof(output); ++i) assert(((unsigned char *)output)[i] == 0xa5);
  free(scratch);
  printf("QUANT_STRIDED_HOST_PASS cases=%u bit_exact=1 panel_reuse=1 bounded_copy=1 failure_no_retry=1\n", cases);
  return 0;
}
