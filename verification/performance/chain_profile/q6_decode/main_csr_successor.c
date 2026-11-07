/* CSR measurement successor of pinned main.c. The llama/SDK work is unchanged. */
#include <stdint.h>
#include <string.h>

#include "qbs/qbs.h"
#include "profile_config.h"
#include "printf.h"

#if !defined(__riscv_vector)
#error This workload requires the real llama RVV quantizer
#endif

enum { K = 2048, N = 64, KB = 8, Q8_BYTES = 292 * KB, W_BYTES = 210 * KB * N,
       GUARD = 64, GUARDS = 8 };
extern const float profile_input[K];
extern const unsigned char profile_weights[W_BYTES];
extern const unsigned char profile_q8_expected[Q8_BYTES];
extern const float profile_expected[N];
extern const unsigned char profile_input_before[GUARD], profile_input_after[GUARD];
extern const unsigned char profile_weights_before[GUARD], profile_weights_after[GUARD];
extern void quantize_row_q8_K(const float *, void *, int64_t);

static struct {
  unsigned char before[GUARD], data[Q8_BYTES], after[GUARD];
} quantized __attribute__((aligned(64)));
static struct {
  unsigned char before[GUARD];
  float data[N];
  unsigned char after[GUARD];
} output __attribute__((aligned(64)));
static unsigned char q8_snapshot[2][Q8_BYTES];
static float output_snapshot[2][N];
static unsigned char guard_snapshot[2][GUARDS][GUARD];

typedef struct {
  uint64_t t0, t1, t2, t3, t4;
  uint64_t fcsr_before, vcsr_before, vstart_before, fcsr_quant;
  uint64_t vcsr_quant, vstart_quant;
  uint64_t fcsr_after, vcsr_after, vstart_after, vl_after, vtype_after;
  unsigned status, context, plan_errors, commands, q8_errors, output_errors;
  unsigned guard_errors, quant_calls, plan_calls, execute_calls;
} trial_t;

static inline uint64_t cycles(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value) : : "memory");
  return value;
}

/* No serializing instruction at phase boundaries. The native executor keeps
   its original pre-command fences, vsetvli and result stores unchanged. */
__attribute__((noinline, noclone))
void q6_decode_trial(unsigned trial, trial_t *r, qbs_plan_t *plan) {
  qbs_device_t device;
  qbs_profile_binding_t binding;
  qbs_execution_options_t options = {0};
  const qbs_problem_t problem = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q6_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 1, .n = N, .k_elements = K,
  };
  uint64_t fcsr_before, vcsr_before, vstart_before, fcsr_quant;
  uint64_t vcsr_quant, vstart_quant;
  uint64_t fcsr_after, vcsr_after, vstart_after, vl_after, vtype_after;
  unsigned quant_calls = 0, plan_calls = 0, execute_calls = 0;
  __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr\ncsrr %2, vstart"
      : "=r"(fcsr_before), "=r"(vcsr_before), "=r"(vstart_before) : : "memory");
  const uint64_t t0 = cycles();
  quantize_row_q8_K(profile_input, quantized.data, K);
  ++quant_calls;
  const uint64_t t1 = cycles();
  /* Quant CSR reads stay after t1 and are charged to admission, with no reset. */
  __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr\ncsrr %2, vstart"
      : "=r"(fcsr_quant), "=r"(vcsr_quant), "=r"(vstart_quant) : : "memory");
  qbs_status_t status = qbs_device_query(qbs_native_info, NULL, &device);
  if (status == QBS_STATUS_OK)
    status = qbs_device_bind_encodings(&device, QBS_WEIGHT_ENCODING_Q6_K,
                                       QBS_ACTIVATION_ENCODING_Q8_K, &binding);
  if (status == QBS_STATUS_OK) {
    status = qbs_plan_create(&device, &problem, plan);
    ++plan_calls;
  }
  if (status == QBS_STATUS_OK &&
      (plan->split_k || plan->needs_activation_gather || plan->workspace_bytes ||
       plan->command_n != 32 || plan->k_blocks != KB))
    status = QBS_STATUS_SHAPE;
  if (status == QBS_STATUS_OK && qbs_plan_supports_activation_context(plan)) {
    options.use_activation_context = 1;
    options.activation_context.context_id = 0;
    options.activation_context.generation = trial + 1;
    options.activation_context_scope = QBS_ACTIVATION_CONTEXT_SCOPE_OPERATION;
  }
  const uint64_t t2 = cycles();
  if (status == QBS_STATUS_OK) {
    status = qbs_execute_with_options(
        plan, profile_weights, W_BYTES, quantized.data, Q8_BYTES, output.data, N, N,
        NULL, 0, &options, qbs_native_execute_command, NULL);
    ++execute_calls;
  }
  const uint64_t t3 = cycles();
  __asm__ volatile("fence rw, rw" : : : "memory");
  const uint64_t t4 = cycles();
  __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr\ncsrr %2, vstart\n"
                   "csrr %3, vl\ncsrr %4, vtype"
      : "=r"(fcsr_after), "=r"(vcsr_after), "=r"(vstart_after),
        "=r"(vl_after), "=r"(vtype_after) : : "memory");
  *r = (trial_t){.t0=t0, .t1=t1, .t2=t2, .t3=t3, .t4=t4,
                 .status=status, .context=options.use_activation_context,
                 .fcsr_before=fcsr_before, .vcsr_before=vcsr_before, .vstart_before=vstart_before,
                 .fcsr_quant=fcsr_quant, .vcsr_quant=vcsr_quant, .vstart_quant=vstart_quant,
                 .fcsr_after=fcsr_after, .vcsr_after=vcsr_after,
                 .vstart_after=vstart_after, .vl_after=vl_after, .vtype_after=vtype_after,
                 .quant_calls=quant_calls, .plan_calls=plan_calls, .execute_calls=execute_calls};
}

static uint32_t bits(float value) {
  uint32_t result;
  memcpy(&result, &value, sizeof(result));
  return result;
}

int main(void) {
  trial_t trials[2] = {0};
  qbs_plan_t plans[2] = {0};
  unsigned errors = 0;
  const unsigned char *const guards[GUARDS] = {
      quantized.before, quantized.after, output.before, output.after,
      profile_input_before, profile_input_after, profile_weights_before, profile_weights_after,
  };
  for (unsigned t = 0; t < 2; ++t) {
    memset(quantized.before, 0xa5, GUARD);
    memset(quantized.after, 0xa5, GUARD);
    memset(output.before, 0xa5, GUARD);
    memset(output.after, 0xa5, GUARD);
    memset(quantized.data, 0x6d, Q8_BYTES);
    for (unsigned i = 0; i < N; ++i) {
      const uint32_t poison = 0x7fc0beef;
      memcpy(&output.data[i], &poison, sizeof(poison));
    }
    __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0" : : : "memory");
    q6_decode_trial(t, &trials[t], &plans[t]);
    trial_t *r = &trials[t];
    memcpy(q8_snapshot[t], quantized.data, Q8_BYTES);
    memcpy(output_snapshot[t], output.data, sizeof(output.data));
    for (unsigned g = 0; g < GUARDS; ++g) {
      memcpy(guard_snapshot[t][g], guards[g], GUARD);
      for (unsigned i = 0; i < GUARD; ++i)
        r->guard_errors += guard_snapshot[t][g][i] != 0xa5;
    }
    for (unsigned i = 0; i < Q8_BYTES; ++i)
      r->q8_errors += q8_snapshot[t][i] != profile_q8_expected[i];
    for (unsigned i = 0; i < N; ++i)
      r->output_errors += bits(output_snapshot[t][i]) != bits(profile_expected[i]);
    if (!r->status) {
      qbs_plan_cursor_t cursor;
      qbs_plan_cursor_reset(&cursor);
      for (;;) {
        qbs_command_t command;
        int has = 0;
        if (qbs_plan_next(&plans[t], &cursor, &command, &has) != QBS_STATUS_OK) {
          ++r->plan_errors;
          break;
        }
        if (!has) break;
        const unsigned i = r->commands++;
        r->plan_errors += i >= 2 || command.m != 1 || command.n != 32 ||
            command.k_blocks != KB || command.k_block_start != 0 ||
            command.output_start != 32 * i || command.input_start != 0 ||
            command.weight_offset_bytes != 32 * i * KB * 210 ||
            command.activation_offset_bytes != 0 || command.accumulate ||
            command.gather_activation;
      }
    }
    errors += r->status != 0 || r->plan_errors || r->commands != 2 ||
              r->q8_errors || r->output_errors || r->guard_errors ||
              r->quant_calls != 1 || r->plan_calls != 1 || r->execute_calls != 1 ||
              r->fcsr_before || r->vcsr_before || r->vstart_before ||
              (r->fcsr_quant & ~UINT64_C(3)) || r->fcsr_after != r->fcsr_quant ||
              r->vcsr_quant != 2 || r->vstart_quant ||
              r->vcsr_after != r->vcsr_quant || r->vstart_after ||
              r->vl_after != 32 || r->vtype_after != 208;
  }
  /* All UART and numerical checking is outside both timed calls. The second
     call is a repeat, not an assertion that any particular cache is warm. */
  printf("Q6_DECODE_META build_id=%s m=1 k=2048 n=64 profile=2 trials=2 q8_bytes=2336 guard_bytes=64\n",
         Q6_BUILD_ID);
  for (unsigned t = 0; t < 2; ++t) {
    const trial_t *r = &trials[t];
    printf("Q6_DECODE_TRIAL trial=%u context=%u status=%u commands=%u plan_errors=%u "
           "q8_errors=%u output_errors=%u t0=%lu t1=%lu t2=%lu t3=%lu t4=%lu "
           "prep=%lu admit=%lu execute=%lu drain=%lu total=%lu\n",
           t, r->context, r->status, r->commands, r->plan_errors,
           r->q8_errors, r->output_errors, (unsigned long)r->t0,
           (unsigned long)r->t1, (unsigned long)r->t2, (unsigned long)r->t3,
           (unsigned long)r->t4, (unsigned long)(r->t1-r->t0),
           (unsigned long)(r->t2-r->t1), (unsigned long)(r->t3-r->t2),
           (unsigned long)(r->t4-r->t3), (unsigned long)(r->t4-r->t0));
    printf("Q6_DECODE_CSR trial=%u fcsr_before=%lu vcsr_before=%lu vstart_before=%lu "
           "fcsr_quant=%lu vcsr_quant=%lu vstart_quant=%lu "
           "fcsr_after=%lu vcsr_after=%lu vstart_after=%lu vl_after=%lu vtype_after=%lu\n",
           t, (unsigned long)r->fcsr_before, (unsigned long)r->vcsr_before,
           (unsigned long)r->vstart_before, (unsigned long)r->fcsr_quant,
           (unsigned long)r->vcsr_quant, (unsigned long)r->vstart_quant,
           (unsigned long)r->fcsr_after, (unsigned long)r->vcsr_after,
           (unsigned long)r->vstart_after, (unsigned long)r->vl_after, (unsigned long)r->vtype_after);
    printf("Q6_DECODE_WORK trial=%u quant_calls=%u plan_calls=%u execute_calls=%u "
           "planned_commands=%u k_elements=2048 n_elements=64 guard_errors=%u\n",
           t, r->quant_calls, r->plan_calls, r->execute_calls, r->commands, r->guard_errors);
    for (unsigned g = 0; g < GUARDS; ++g) {
      printf("Q6_DECODE_GUARD trial=%u index=%u hex=", t, g);
      for (unsigned i = 0; i < GUARD; ++i)
        printf("%02x", (unsigned)guard_snapshot[t][g][i]);
      printf("\n");
    }
    for (unsigned b = 0; b < KB; ++b) {
      printf("Q6_DECODE_Q8 trial=%u block=%u hex=", t, b);
      for (unsigned i = 0; i < 292; ++i) printf("%02x", (unsigned)q8_snapshot[t][292*b+i]);
      printf("\n");
    }
    for (unsigned i = 0; i < N; ++i)
      printf("Q6_DECODE_OUT trial=%u index=%u bits=%08x\n", t, i,
             (unsigned)bits(output_snapshot[t][i]));
  }
  printf("Q6_DECODE_DONE errors=%u trials=2 commands=4\n", errors);
  return errors != 0;
}
