/* Reuse sealed fixture data/guards/trap support, not its workload entry. */
#define main archived_main
#include "../reader_handoff/main.c"
#undef main

extern void rf_qbs_only(const qbs_descriptor_t *, const void *, const uint32_t *, uint32_t *);
static uint16_t fault_query[8][64] __attribute__((aligned(64)));

static int rf_qbs(unsigned access) {
  descriptor(access, (uintptr_t)weights);
  poison(&qo);
  uint64_t before = rh_trap_count;
  rf_qbs_only(&qdesc, access >= QBS_ACTIVATION_ACCESS_REUSE ? NULL : &activation,
              seed, qo.data.u32);
  if (rh_trap_count != before || guards(&qo)) return fail("rf_qbs_trap_or_guard");
  const uint32_t expected[3] = {0x43800000, 0x44000000, 0x44400000};
  for (unsigned i = 0; i < 32; ++i)
    if (qo.data.u32[i] != (i < 3 ? expected[i] : 0)) return fail("rf_qbs_payload");
  return 0;
}

int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb != 128 || rh_trap_count ||
      rh_qbs_info(3) != qbs_capability_word(3, VLEN) ||
      rh_akv_info(2) != akv_v2_capability_word(2, 1)) return fail("rf_capability");
  for (unsigned i = 0; i < 32; ++i) seed[i] = UINT32_C(0x41800000) + i;
  for (unsigned r = 0; r < 3; ++r) {
    weights[r].d = 0x3c00;
    for (unsigned i = 0; i < 4; ++i) weights[r].scales[i] = weights[r].scales[i+8] = 1;
    for (unsigned i = 0; i < 128; ++i) weights[r].qs[i] = (uint8_t)((r+1)*0x11);
  }
  activation.d = 1.0f;
  for (unsigned i = 0; i < 256; ++i) activation.qs[i] = 1;
  for (unsigned i = 0; i < 16; ++i) activation.bsums[i] = 16;
  printf("READER_FAULT_BEGIN qbs=3 akv=11 fault_owner=akv qbs_context=1 fault_q_rows=8\n");
  if (ordinary() || rf_qbs(QBS_ACTIVATION_ACCESS_FILL)) return 1;
  activation.d = 2.0f;
  for (unsigned i = 0; i < 256; ++i) activation.qs[i] = 7;
  for (unsigned i = 0; i < 16; ++i) activation.bsums[i] = 112;
  setup_akv(0);
  /* Eight Q ranges exceed the two-burst reader capacity: older Q payload
     must progress before the planner reaches the deliberately invalid K. */
  for (unsigned row = 0; row < 8; ++row)
    for (unsigned d = 0; d < 64; ++d) fault_query[row][d] = sample(0, 0, row, d);
  adesc.q_rows = 8;
  adesc.q_base = (uintptr_t)fault_query;
  adesc.k_base = 0;
  __asm__ volatile("fence rw,rw" : : : "memory");
  rh_akv_full(&adesc);
  /* The sealed .option norvc wrapper has li, fence, then the faulting word. */
  if (rh_trap_count != 1 || rh_trap_cause != 5 || rh_trap_tval != 0 ||
      rh_trap_epc != (uintptr_t)rh_akv_full + 8) return fail("rf_akv_fault_identity");
  if (rf_qbs(QBS_ACTIVATION_ACCESS_REUSE)) return 1;
  setup_akv(1);
  rh_akv_full(&adesc);
  if (rh_trap_count != 1) return fail("rf_akv_retry");
  poison_akv();
  for (unsigned stream = 0; stream < 3; ++stream)
    for (unsigned row = 0; row < (stream == 0 ? 2u : 3u); ++row) {
      poison(&ao);
      rh_akv_load(akv_v2_selector((akv_stream_t)stream, row), ao.data.u16);
      if (rh_trap_count != 1 || row_equal(1, stream, row)) return fail("rf_resident");
    }
  if (rf_qbs(QBS_ACTIVATION_ACCESS_RELEASE)) return 1;
  rh_akv_release();
  if (ordinary() || rh_trap_count != 1 || rows_checked != 8) return fail("rf_final");
  printf("READER_FAULT_PASS qbs=3 akv=11 traps=1 cause=5 tval=0 rows=8 qbs_words=96\n");
  return 0;
}
