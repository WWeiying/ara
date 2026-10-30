/* Reuse the reviewed descriptor oracle and deterministic input fixtures. */
#define main decode_contract_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "native_prefix.h"

typedef struct { quant_prefill_native_context_t *context; unsigned row; } row_context_t;
static int row_qk(void *opaque, unsigned first, unsigned rows, unsigned token,
    unsigned tokens, float *scores, size_t stride) {
  row_context_t *r = opaque;
  assert(first == 0 && rows == 1);
  return quant_prefill_native_qk(r->context, r->row, rows, token, tokens, scores, stride);
}
static int row_value(void *opaque, unsigned token, float *value, unsigned dim) {
  row_context_t *r = opaque;
  return quant_prefill_native_value(r->context, token, value, dim);
}

int main(void) {
  assert(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  const unsigned dims[] = {32, 96, 128};
  const unsigned prefixes[][8] = {
    {1, 2, 3, 4, 5, 6, 7, 8},
    {31, 31, 32, 32, 33, 33, 65, 65},
    {65, 33, 32, 31, 3, 2, 1, 65},
    {65, 65, 65, 65, 65, 65, 65, 65},
  };
  unsigned cases = 0, aligned = 0;
  for (unsigned d = 0; d < 3; ++d)
    for (unsigned format = 0; format < 2; ++format)
      for (unsigned pattern = 0; pattern < 4; ++pattern) {
        akv_quant_selection_input_t p = prepare(dims[d], 8, 1, 65, format);
        akv_quant_selection_t selection;
        assert(akv_quant_select(&p, &selection) == AKV_QUANT_SELECT_OK);
        executor_t executor = {.input = &p};
        akv_quant_native_bindings_t bindings = {quantize, decode, scale, mad, execute, &executor};
        akv_quant_native_report_t report = {0};
        quant_prefill_native_context_t c = {
          .core = {&p, &bindings, &selection, &workspace, &report, 0},
          .visible = prefixes[pattern]};
        for (unsigned row = 0; row < 8; ++row)
          quantize(query[row], workspace.query + row * selection.query_quant_row_bytes, dims[d]);
        unsigned expected_decodes = 0, max_prefix = 0;
        for (unsigned row = 0; row < 8; ++row) {
          row_context_t one = {&c, row};
          akv_quant_online_plan_t plan = {1, dims[d], c.visible[row], p.scale,
            &one, row_qk, row_value, scale, mad};
          assert(akv_quant_online_head_major(&plan, reference[row], 136,
                                              &reference_workspace.online) == AKV_QUANT_OK);
          expected_decodes += c.visible[row];
          if (c.visible[row] > max_prefix) max_prefix = c.visible[row];
        }
        assert(report.value_decodes == expected_decodes);
        executor.calls = 0; memset(&report, 0, sizeof(report)); c.alignment_copies = 0;
        akv_quant_online_plan_t plan = {8, dims[d], 65, p.scale, &c,
          quant_prefill_native_qk, quant_prefill_native_value, scale, mad};
        assert(quant_prefill_prefix_schedule(&plan, c.visible, output[0], 136,
                                               &workspace.online) == AKV_QUANT_OK);
        assert(!memcmp(output, reference, sizeof(output)));
        assert(report.value_decodes == max_prefix && report.command_attempts == executor.calls);
        if (dims[d] == 128 || pattern == 3) assert(c.alignment_copies == 0);
        if (dims[d] != 128 && pattern == 0) assert(c.alignment_copies != 0);
        aligned += c.alignment_copies;
        // Prefix rejection cannot issue a descriptor or consume a value.
        unsigned before = executor.calls;
        assert(quant_prefill_native_qk(&c, 0, 1, c.visible[0], 1, output[0], 136));
        assert(executor.calls == before);
        executor.calls = 0; executor.fail_at = 1; memset(&report, 0, sizeof(report));
        assert(quant_prefill_prefix_schedule(&plan, c.visible, output[0], 136,
                                               &workspace.online) == AKV_QUANT_QK_FAILED);
        assert(executor.calls == 1 && report.command_attempts == 1 && !report.value_decodes);
        ++cases;
      }
  assert(aligned);
  printf("NATIVE_PREFIX_PASS cases=%u alignment_copies=%u reference=qbs_ref hardware=not_executed\n",
         cases, aligned);
}
