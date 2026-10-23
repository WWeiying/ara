#include <stddef.h>
#include <stdint.h>

#include "akv_abi.h"
#include "printf.h"

enum { D = 128, TOKENS = 72, FIRST = 64, TAIL = 8, GUARD = 16 };
typedef struct {
  uint64_t start, returned, drained, vl, fflags, vstart;
} markers_t;
_Static_assert(sizeof(markers_t) == 48 && offsetof(markers_t, vstart) == 40,
               "probe.S marker offsets");
_Static_assert(AKV_DESCRIPTOR_BYTES == 64 && AKV_V2_TILE_TOKENS == FIRST &&
                   AKV_HEAD_DIM_128 == D, "fixed probe geometry");

extern uint64_t probe_info(uint64_t index);
extern uint64_t probe_vector_bytes(void);
extern void probe_full(const akv_descriptor_t *, uint64_t tile_start);
extern void probe_release(void);
extern uint64_t probe_row(uint64_t selector, uint16_t *output);
extern uint64_t probe_canary(const uint32_t *input, uint32_t *output);
extern void probe_immediate(uint64_t tile, uint32_t *output, markers_t *markers);
extern void probe_serial(uint64_t tile, uint32_t *output, markers_t *markers);
extern void _fail(uint64_t status) __attribute__((noreturn));

/* Explicitly initialized in rvtest_init: common startup does not clear BSS. */
volatile uint64_t probe_boot_consistency;
static uint16_t query[D] __attribute__((aligned(64)));
static uint16_t key[TOKENS][D] __attribute__((aligned(64)));
static uint16_t value[TOKENS][D] __attribute__((aligned(64)));
static akv_descriptor_t descriptor __attribute__((aligned(64)));
static struct {
  uint32_t before[GUARD];
  uint16_t data[D];
  uint32_t after[GUARD];
} row __attribute__((aligned(64)));
static struct {
  uint32_t before[GUARD], data[D], after[GUARD];
} arithmetic __attribute__((aligned(64)));
static struct {
  uint32_t before[GUARD], data[32], after[GUARD];
} canary __attribute__((aligned(64)));
static uint32_t canary_input[32] __attribute__((aligned(64)));

__attribute__((noreturn)) void probe_unexpected_trap(
    uint64_t cause, uint64_t pc, uint64_t tval) {
  printf("AKV_REFILL_PROBE_FAIL trap=1 cause=%lx pc=%lx tval=%lx\n",
         cause, pc, tval);
  _fail(1);
}

static int require(int condition, const char *stage) {
  if (condition) return 1;
  printf("AKV_REFILL_PROBE_FAIL stage=%s\n", stage);
  return 0;
}

/* Injective across stream/token/dimension; finite FP16 bit patterns. The
 * checker recomputes these values, not a comparison against mutable DMA input. */
static uint16_t pattern(unsigned stream, unsigned token, unsigned dim) {
  return (uint16_t)(0x0400u + stream * 0x2800u + token * D + dim);
}

static void set_guards(uint32_t *before, uint32_t *after) {
  for (unsigned i = 0; i < GUARD; ++i) {
    before[i] = 0x12ab3400u + i;
    after[i] = 0xcd567800u + i;
  }
}

static int check_guards(const uint32_t *before, const uint32_t *after) {
  for (unsigned i = 0; i < GUARD; ++i)
    if (before[i] != 0x12ab3400u + i || after[i] != 0xcd567800u + i)
      return require(0, "output_guard");
  return 1;
}

static int check_row(unsigned stream, unsigned local, unsigned global,
                     unsigned resident) {
  const uint32_t selector = akv_v2_selector((akv_stream_t)stream, local);
  if (!require(akv_v2_row_selector_is_valid(&descriptor, resident, selector),
               "row_selector")) return 0;
  set_guards(row.before, row.after);
  for (unsigned d = 0; d < D; ++d) row.data[d] = 0xffffu;
  if (!require(probe_row(selector, row.data) == D, "row_vl")) return 0;
  for (unsigned d = 0; d < D; ++d) {
    const uint16_t expected = pattern(stream, global, d);
    if (row.data[d] != expected) {
      printf("AKV_REFILL_PROBE_FAIL stream=%u local=%u global=%u dim=%u"
             " actual=%x expected=%x\n", stream, local, global, d,
             (unsigned)row.data[d], (unsigned)expected);
      return 0;
    }
  }
  return check_guards(row.before, row.after);
}

static int check_tile(unsigned start, unsigned count) {
  if (!check_row(AKV_STREAM_Q, 0, 0, count)) return 0;
  for (unsigned token = 0; token < count; ++token) {
    if (!check_row(AKV_STREAM_K, token, start + token, count) ||
        !check_row(AKV_STREAM_V, token, start + token, count)) return 0;
  }
  return 1;
}

static int check_old_tile(void) {
  static const unsigned tokens[] = {0, 31, 63};
  if (!check_row(AKV_STREAM_Q, 0, 0, FIRST)) return 0;
  for (unsigned i = 0; i < sizeof(tokens) / sizeof(tokens[0]); ++i) {
    const unsigned token = tokens[i];
    if (!check_row(AKV_STREAM_K, token, token, FIRST) ||
        !check_row(AKV_STREAM_V, token, token, FIRST)) return 0;
  }
  return 1;
}

static int check_canary(unsigned seed) {
  set_guards(canary.before, canary.after);
  for (unsigned i = 0; i < 32; ++i) {
    canary_input[i] = seed + 3u * i;
    canary.data[i] = 0xdeadbeefu;
  }
  if (!require(probe_canary(canary_input, canary.data) == 32, "canary_vl"))
    return 0;
  for (unsigned i = 0; i < 32; ++i)
    if (!require(canary.data[i] == seed + 3u * i + 1u &&
                     canary_input[i] == seed + 3u * i, "rvv_canary")) return 0;
  return check_guards(canary.before, canary.after);
}

static int check_sources(void) {
  for (unsigned d = 0; d < D; ++d)
    if (!require(query[d] == pattern(AKV_STREAM_Q, 0, d), "query_mutated"))
      return 0;
  for (unsigned t = 0; t < TOKENS; ++t)
    for (unsigned d = 0; d < D; ++d)
      if (!require(key[t][d] == pattern(AKV_STREAM_K, t, d) &&
                       value[t][d] == pattern(AKV_STREAM_V, t, d),
                   "kv_mutated")) return 0;
  return 1;
}

static int check_encodings(void) {
  return require(
      akv_encode_info(10, 10) == 0x0005455bu &&
      akv_encode_v2_fill(10, 11, AKV_FILL_FULL) == 0x00b5605bu &&
      akv_encode_v2_fill(0, 10, AKV_FILL_REFILL) == 0x02a0605bu &&
      akv_encode_load(8, 10, D) == 0x0205345bu &&
      akv_encode_release() == 0x0000505bu, "instruction_encodings");
}

static int run_mode(unsigned serial) {
  const char *name = serial ? "serial" : "immediate";
  markers_t markers = {0};
  printf("AKV_REFILL_PROBE_BEGIN mode=%s d=128 q_rows=1 kv_length=72"
         " tile_start=64 tile_count=8 fmas=16 elements=128\n", name);
  probe_full(&descriptor, 0);
  if (!check_old_tile()) return 0;
  set_guards(arithmetic.before, arithmetic.after);
  for (unsigned d = 0; d < D; ++d) arithmetic.data[d] = 0xdeadbeefu;
  if (serial) probe_serial(FIRST, arithmetic.data, &markers);
  else probe_immediate(FIRST, arithmetic.data, &markers);
  if (!require(markers.vl == D && markers.fflags == 8 && markers.vstart == 0,
               "arithmetic_state") ||
      !require(markers.start < markers.returned &&
                   markers.returned < markers.drained, "cycle_markers")) return 0;
  for (unsigned d = 0; d < D; ++d) {
    if (arithmetic.data[d] != 0x41800000u) {
      printf("AKV_REFILL_PROBE_FAIL mode=%s arithmetic_dim=%u actual=%x"
             " expected=41800000\n", name, d, arithmetic.data[d]);
      return 0;
    }
  }
  if (!check_guards(arithmetic.before, arithmetic.after) ||
      !check_tile(FIRST, TAIL) || !check_canary(0x100u + serial * 0x100u))
    return 0;
  probe_release();
  if (!check_canary(0x300u + serial * 0x100u) || !check_sources()) return 0;
  printf("AKV_REFILL_PROBE_CYCLES mode=%s start=%lu returned=%lu drained=%lu"
         " to_return=%lu to_drain=%lu\n", name, markers.start,
         markers.returned, markers.drained, markers.returned - markers.start,
         markers.drained - markers.start);
  printf("AKV_REFILL_PROBE_PASS mode=%s arithmetic=128 fflags=8 vstart=0"
         " q_rows=2 k_rows=11 v_rows=11 canaries=2 traps=0\n", name);
  return 1;
}

int main(void) {
  if (!check_encodings() ||
      !require(probe_boot_consistency == 1, "acc_consistency") ||
      !require(probe_vector_bytes() == 128, "requires_vlen1024")) return 1;
  const uint64_t info0 = probe_info(0), info1 = probe_info(1);
  const uint64_t info2 = probe_info(2), info3 = probe_info(3);
  printf("AKV_REFILL_PROBE_CAPS word0=%016lx word1=%016lx"
         " word2=%016lx word3=%016lx\n", info0, info1, info2, info3);
  /* Require the established v2 feature bits, permit later optional additions. */
  const uint64_t v2_required_mask = (UINT64_C(1) << 38) - 1;
  if (!require(info0 == akv_capability_word(0, 1) &&
                   info1 == akv_capability_word(1, 1) &&
                   (info2 & v2_required_mask) ==
                       (akv_v2_capability_word(2, 1) & v2_required_mask) &&
                   info3 == akv_v2_capability_word(3, 1), "capabilities")) return 1;
  for (unsigned d = 0; d < D; ++d) query[d] = pattern(AKV_STREAM_Q, 0, d);
  for (unsigned t = 0; t < TOKENS; ++t)
    for (unsigned d = 0; d < D; ++d) {
      key[t][d] = pattern(AKV_STREAM_K, t, d);
      value[t][d] = pattern(AKV_STREAM_V, t, d);
    }
  descriptor = (akv_descriptor_t){
      .version = AKV_DESCRIPTOR_VERSION, .element_format = AKV_ELEMENT_FORMAT_F16,
      .q_rows = 1, .head_dim = D, .kv_length = TOKENS,
      .q_row_stride_bytes = 2 * D, .k_token_stride_bytes = 2 * D,
      .v_token_stride_bytes = 2 * D,
      .q_base = (uintptr_t)query, .k_base = (uintptr_t)key,
      .v_base = (uintptr_t)value};
  if (!require(akv_v2_descriptor_is_valid(&descriptor), "descriptor")) return 1;
  printf("AKV_REFILL_PROBE_EXPECT commands=54 v2_full=2 v2_refill=2"
         " load=48 v2_row_load=48 release=2 q_external_bytes=512"
         " kv_external_bytes=73728 replay_bytes=12288 read_ranges=292"
         " read_payload_bytes=74368\n");
  if (!run_mode(0) || !run_mode(1)) return 1;
  printf("AKV_REFILL_PROBE_SUITE_PASS modes=2 traps=0\n");
  return 0;
}
