#include <stdint.h>
#include <string.h>
#include "qbs/qbs.h"
#include "projection_config.h"
#include "printf.h"

enum { M = 8, K = 2048, KB = 8, N = PROJECTION_N,
       AB = M*KB*292, WB = N*KB*144, GUARD = 64, TRIALS = 4 };
extern const float projection_input[M*K];
extern const unsigned char projection_weights[WB], projection_expected_q8[AB];
extern const float projection_expected[M*N];
extern const unsigned projection_flags;
extern void quantize_row_q8_K(const float *, void *, int64_t);

static struct {
  unsigned char before[GUARD], data[AB], after[GUARD];
} q8 __attribute__((aligned(64))), packed __attribute__((aligned(64)));
static struct {
  unsigned char before[GUARD];
  float data[M*N];
  unsigned char after[GUARD];
} output __attribute__((aligned(64)));
static float snapshots[TRIALS][M*N];
static unsigned char q8_snapshots[TRIALS][AB];

typedef struct {
  uint64_t t[6], flags;
  unsigned mode, status, commands, context, outputs_bad, q8_bad, guards_bad;
} record_t;

static inline uint64_t cycles(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value) : : "memory");
  return value;
}

__attribute__((noinline, noclone))
static void projection_trial(unsigned mode, record_t *r) {
  qbs_device_t device;
  qbs_plan_t plan;
  qbs_execution_options_t options = {0};
  const qbs_problem_t problem = {
    .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
    .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
    .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
    .activation_storage = mode == 8 ? QBS_ACTIVATION_STORAGE_M8_GROUPED
                                   : QBS_ACTIVATION_STORAGE_M4_GROUPED,
    .m = M, .n = N, .k_elements = K,
  };
  r->mode = mode;
  r->t[0] = cycles();
  for (unsigned row = 0; row < M; ++row)
    quantize_row_q8_K(projection_input + row*K, q8.data + row*KB*292, K);
  r->t[1] = cycles();
  qbs_status_t status;
  if (mode == 8)
    status = qbs_pack_activation_m8_grouped(QBS_ACTIVATION_PROFILE_Q8_K,
        q8.data, AB, M, KB, packed.data, AB);
  else {
    status = QBS_STATUS_OK;
    for (unsigned row = 0; row < M && status == QBS_STATUS_OK; row += 4)
      status = qbs_pack_activation_m4(QBS_ACTIVATION_PROFILE_Q8_K,
          q8.data + row*KB*292, 4*KB*292, KB, packed.data + row*KB*292, 4*KB*292);
  }
  r->t[2] = cycles();
  if (status == QBS_STATUS_OK) status = qbs_device_query(qbs_native_info, NULL, &device);
  if (status == QBS_STATUS_OK) status = qbs_plan_create(&device, &problem, &plan);
  r->commands = mode == 8 ? N/16 : 2*(N/32);
  if (status == QBS_STATUS_OK &&
      (plan.split_k || plan.needs_activation_gather || plan.workspace_bytes ||
       plan.command_m != mode || plan.command_n != (mode == 8 ? 16 : 32) ||
       plan.k_blocks != KB || qbs_plan_supports_activation_context(&plan)))
    status = QBS_STATUS_SHAPE;
  r->context = 0;
  r->t[3] = cycles();
  __asm__ volatile("csrwi fflags, 1" : : : "memory");
  if (status == QBS_STATUS_OK)
    status = qbs_execute_with_options(&plan, projection_weights, WB,
        packed.data, AB, output.data, M*N, N, NULL, 0, &options,
        qbs_native_execute_command, NULL);
  r->t[4] = cycles();
  __asm__ volatile("fence rw, rw" : : : "memory");
  r->t[5] = cycles();
  __asm__ volatile("csrr %0, fflags" : "=r"(r->flags) : : "memory");
  r->status = status;
}

static unsigned bits(float value) {
  unsigned result;
  memcpy(&result, &value, sizeof(result));
  return result;
}

int main(void) {
  record_t records[TRIALS] = {0};
  memset(q8.before, 0xa5, GUARD); memset(q8.after, 0xa5, GUARD);
  memset(packed.before, 0xa5, GUARD); memset(packed.after, 0xa5, GUARD);
  memset(output.before, 0xa5, GUARD); memset(output.after, 0xa5, GUARD);
  __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0" : : : "memory");
  for (unsigned trial = 0; trial < TRIALS; ++trial) {
    memset(output.data, 0x5a, sizeof(output.data));
    projection_trial(trial == 0 || trial == 3 ? 4 : 8, &records[trial]);
    memcpy(snapshots[trial], output.data, sizeof(output.data));
    memcpy(q8_snapshots[trial], q8.data, AB);
    for (unsigned i = 0; i < GUARD; ++i)
      records[trial].guards_bad += q8.before[i] != 0xa5 || q8.after[i] != 0xa5 ||
          packed.before[i] != 0xa5 || packed.after[i] != 0xa5 ||
          output.before[i] != 0xa5 || output.after[i] != 0xa5;
  }
  unsigned errors = 0;
  printf("STAGE2_PROJECTION_META id=%s m=8 k=2048 n=%u trials=4 whole_model=0\n",
         PROJECTION_ID, N);
  for (unsigned trial = 0; trial < TRIALS; ++trial) {
    record_t *r = &records[trial];
    for (unsigned i = 0; i < AB; ++i)
      r->q8_bad += q8_snapshots[trial][i] != projection_expected_q8[i];
    for (unsigned i = 0; i < M*N; ++i)
      r->outputs_bad += bits(snapshots[trial][i]) != bits(projection_expected[i]);
    errors += r->status != QBS_STATUS_OK || r->guards_bad || r->q8_bad ||
              r->outputs_bad || r->flags != (projection_flags | 1u);
    printf("STAGE2_PROJECTION_TRIAL id=%u mode=%u status=%u commands=%u context=%u "
           "quant=%lu pack=%lu plan=%lu execute=%lu drain=%lu total=%lu "
           "flags=%lu expected_flags=%u q8_bad=%u output_bad=%u guards_bad=%u\n",
           trial, r->mode, r->status, r->commands, r->context,
           r->t[1]-r->t[0], r->t[2]-r->t[1], r->t[3]-r->t[2],
           r->t[4]-r->t[3], r->t[5]-r->t[4], r->t[5]-r->t[0],
           r->flags, projection_flags | 1u, r->q8_bad, r->outputs_bad, r->guards_bad);
    for (unsigned row = 0; row < M; ++row)
      for (unsigned col = 0; col < N; ++col)
        printf("STAGE2_PROJECTION_OUTPUT trial=%u row=%u col=%u bits=%08x\n",
               trial, row, col, bits(snapshots[trial][row*N+col]));
  }
  printf("STAGE2_PROJECTION_%s errors=%u\n", errors ? "FAIL" : "PASS", errors);
  return errors != 0;
}
