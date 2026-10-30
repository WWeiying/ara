#include <stddef.h>
#include <stdint.h>
#include "akv_abi.h"
#include "qbs_abi.h"
#include "printf.h"

#if !defined(VLEN) || VLEN != 1024 || !defined(NR_LANES) || NR_LANES != 4
#error "reader handoff fixture requires VLEN1024 and four lanes"
#endif

typedef struct { uint16_t d, dmin; uint8_t scales[12], qs[128]; } block_q4;
typedef struct { float d; int8_t qs[256]; int16_t bsums[16]; } block_q8;
_Static_assert(sizeof(block_q4)==QBS_Q4_K_BLOCK_BYTES,"Q4_K size");
_Static_assert(sizeof(block_q8)==QBS_Q8_K_BLOCK_BYTES,"Q8_K size");
typedef struct {
  uint64_t before[8];
  union { uint32_t u32[32]; uint16_t u16[64]; } data;
  uint64_t after[8];
} guarded_output;
_Static_assert(offsetof(guarded_output,data)==64 && offsetof(guarded_output,after)==192,
               "exact output bounds");

volatile uint64_t rh_trap_count, rh_trap_cause, rh_trap_tval, rh_trap_epc;
extern void rh_trap_handler(void), rh_qbs_site(void);
extern uint64_t rh_qbs_info(uint64_t), rh_akv_info(uint64_t);
extern uint64_t rh_qbs_then_akv(const qbs_descriptor_t *, const void *,
    const uint32_t *, uint32_t *, uint16_t *);
extern void rh_akv_full(const akv_descriptor_t *);
extern void rh_akv_load(uint64_t, uint16_t *), rh_akv_release(void);
extern void rh_rvv_copy_add(const uint32_t *, uint32_t *);

static block_q4 weights[3] __attribute__((aligned(64)));
static block_q8 activation __attribute__((aligned(64)));
static qbs_descriptor_t qdesc __attribute__((aligned(64)));
static akv_descriptor_t adesc __attribute__((aligned(64)));
static uint16_t query[2][64] __attribute__((aligned(64)));
static uint16_t key[3][64] __attribute__((aligned(64)));
static uint16_t value[3][64] __attribute__((aligned(64)));
static uint32_t seed[32] __attribute__((aligned(64)));
static guarded_output qo __attribute__((aligned(64))), ao __attribute__((aligned(64)));
static unsigned qbs_commands, akv_commands, rows_checked, words_checked;

void rvtest_init(void) {
  __asm__ volatile("csrw mtvec,%0" : : "r"(rh_trap_handler) : "memory");
}

static int fail(const char *stage) {
  printf("READER_HANDOFF_FAIL stage=%s traps=%lu cause=%lu tval=%lx epc=%lx\n",
      stage,(unsigned long)rh_trap_count,(unsigned long)rh_trap_cause,
      (unsigned long)rh_trap_tval,(unsigned long)rh_trap_epc);
  return 1;
}
static void poison(guarded_output *o) {
  for (unsigned i=0;i<8;++i) o->before[i]=o->after[i]=UINT64_C(0xa55aa55a12344321);
  for (unsigned i=0;i<32;++i) o->data.u32[i]=UINT32_C(0xdeadbeef);
}
static int guards(const guarded_output *o) {
  for (unsigned i=0;i<8;++i)
    if (o->before[i]!=UINT64_C(0xa55aa55a12344321) ||
        o->after[i]!=UINT64_C(0xa55aa55a12344321)) return 1;
  return 0;
}
static uint16_t sample(unsigned epoch, unsigned stream, unsigned row, unsigned d) {
  return (uint16_t)(0x1000+epoch*0x800+stream*0x1000+row*0x100+d);
}
static void setup_akv(unsigned epoch) {
  for (unsigned r=0;r<2;++r)
    for (unsigned d=0;d<64;++d) query[r][d]=sample(epoch,0,r,d);
  for (unsigned r=0;r<3;++r)
    for (unsigned d=0;d<64;++d) {
      key[r][d]=sample(epoch,1,r,d); value[r][d]=sample(epoch,2,r,d);
    }
  adesc=(akv_descriptor_t){.version=AKV_DESCRIPTOR_VERSION,
      .element_format=AKV_ELEMENT_FORMAT_F16,.q_rows=2,.head_dim=64,.kv_length=3,
      .q_row_stride_bytes=128,.k_token_stride_bytes=128,.v_token_stride_bytes=128,
      .q_base=(uintptr_t)query,.k_base=(uintptr_t)key,.v_base=(uintptr_t)value};
}
static void poison_akv(void) {
  for (unsigned r=0;r<2;++r)
    for (unsigned d=0;d<64;++d) query[r][d]=0x7e01;
  for (unsigned r=0;r<3;++r)
    for (unsigned d=0;d<64;++d) key[r][d]=value[r][d]=0x7e02;
  __asm__ volatile("fence rw,rw" : : : "memory");
}
static int row_equal(unsigned epoch, unsigned stream, unsigned row) {
  if (guards(&ao)) return fail("akv_guard");
  for (unsigned d=0;d<64;++d)
    if (ao.data.u16[d]!=sample(epoch,stream,row,d)) return fail("akv_payload");
  ++rows_checked;
  return 0;
}
static int resident(unsigned stage, unsigned epoch) {
  const uint64_t before=rh_trap_count;
  for (unsigned stream=0;stream<3;++stream)
    for (unsigned row=0;row<(stream==0 ? 2u : 3u);++row) {
      poison(&ao);
      rh_akv_load(akv_v2_selector((akv_stream_t)stream,row),ao.data.u16);
      ++akv_commands;
      if (rh_trap_count!=before || row_equal(epoch,stream,row)) return fail("resident");
    }
  printf("READER_HANDOFF_RESIDENT stage=%u epoch=%u rows=8 bytes=1024 external_poison=1\n",stage,epoch);
  return 0;
}
static void descriptor(unsigned access, uintptr_t weight_base) {
  const qbs_descriptor_fields_t f={.descriptor_version=QBS_DESCRIPTOR_VERSION,
      .weight_profile=QBS_WEIGHT_PROFILE_Q4_K,.activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout=QBS_WEIGHT_LAYOUT_ROW_MAJOR,.activation_layout=QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n=3,.k_blocks=1,.activation_access=access,.context_id=0,
      .context_generation=access==QBS_ACTIVATION_ACCESS_DIRECT ? 0 : 0x35};
  qdesc=(qbs_descriptor_t){.header=qbs_pack_descriptor_header(&f),.weight_base=weight_base};
}
static int pair(unsigned stage, unsigned access, unsigned fault, unsigned epoch) {
  const uint64_t before=rh_trap_count;
  descriptor(access,fault ? 0 : (uintptr_t)weights);
  poison(&qo); poison(&ao);
  /* REUSE/RELEASE must not issue activation reads, even from address zero. */
  const void *a=access>=QBS_ACTIVATION_ACCESS_REUSE ? NULL : &activation;
  const uint64_t scratch=rh_qbs_then_akv(&qdesc,a,seed,qo.data.u32,ao.data.u16);
  ++qbs_commands; ++akv_commands;
  if (scratch || guards(&qo) || rh_trap_count!=before+fault) return fail("pair_trap_or_guard");
  if (fault && (rh_trap_cause!=5 || rh_trap_tval!=0 ||
      rh_trap_epc!=(uintptr_t)rh_qbs_site)) return fail("payload_fault_identity");
  static const uint32_t expected[3]={0x43800000,0x44000000,0x44400000};
  for (unsigned i=0;i<32;++i) {
    const uint32_t want=fault ? seed[i] : i<3 ? expected[i] : 0;
    if (qo.data.u32[i]!=want) return fail("qbs_destination");
    ++words_checked;
  }
  if (row_equal(epoch,0,1)) return 1;
  printf("READER_HANDOFF_PAIR stage=%u access=%u fault=%u qbs_words=32 akv_row=1 scratch_preserved=1\n",
      stage,access,fault);
  return 0;
}
static int full(unsigned epoch) {
  const uint64_t before=rh_trap_count;
  setup_akv(epoch); rh_akv_full(&adesc); ++akv_commands;
  if (rh_trap_count!=before) return fail("akv_full");
  poison_akv();
  return 0;
}
static int ordinary(void) {
  const uint64_t before=rh_trap_count;
  poison(&qo); rh_rvv_copy_add(seed,qo.data.u32);
  if (rh_trap_count!=before || guards(&qo)) return fail("ordinary_trap_or_guard");
  for (unsigned i=0;i<32;++i)
    if (qo.data.u32[i]!=seed[i]+1) return fail("ordinary_result");
  return 0;
}
int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb!=128 || rh_trap_count) return fail("vector_configuration");
  if (rh_qbs_info(0)!=qbs_capability_word(0,VLEN) || rh_trap_count ||
      rh_qbs_info(2)!=qbs_capability_word(2,VLEN) || rh_trap_count ||
      rh_qbs_info(3)!=qbs_capability_word(3,VLEN) || rh_trap_count ||
      rh_akv_info(2)!=akv_v2_capability_word(2,1) || rh_trap_count)
    return fail("capability");
  for (unsigned i=0;i<32;++i) seed[i]=UINT32_C(0x41800000)+i;
  for (unsigned r=0;r<3;++r) {
    weights[r].d=0x3c00;
    for (unsigned i=0;i<4;++i) weights[r].scales[i]=weights[r].scales[i+8]=1;
    for (unsigned i=0;i<128;++i) weights[r].qs[i]=(uint8_t)((r+1)*0x11);
  }
  activation.d=1.0f;
  for (unsigned i=0;i<256;++i) activation.qs[i]=1;
  for (unsigned i=0;i<16;++i) activation.bsums[i]=16;
  printf("READER_HANDOFF_BEGIN synthetic=1 lanes=4 vlen=1024 qbs_m=1 n=3 kb=1 akv_d=64 context_test=1\n");
  if (ordinary() || full(0) || resident(0,0)) return 1;
  if (pair(0,QBS_ACTIVATION_ACCESS_DIRECT,0,0) || resident(1,0)) return 1;
  if (pair(1,QBS_ACTIVATION_ACCESS_DIRECT,1,0) || resident(2,0)) return 1;
  if (pair(2,QBS_ACTIVATION_ACCESS_DIRECT,0,0) || resident(3,0)) return 1;
  if (pair(3,QBS_ACTIVATION_ACCESS_FILL,0,0)) return 1;
  activation.d=2.0f;
  for (unsigned i=0;i<256;++i) activation.qs[i]=7;
  for (unsigned i=0;i<16;++i) activation.bsums[i]=112;
  /* A second FULL really uses the reader between QBS FILL and REUSE. */
  if (full(1) || resident(4,1)) return 1;
  if (pair(4,QBS_ACTIVATION_ACCESS_REUSE,0,1) || resident(5,1)) return 1;
  if (pair(5,QBS_ACTIVATION_ACCESS_RELEASE,0,1) || resident(6,1)) return 1;
  rh_akv_release(); ++akv_commands;
  if (ordinary() || rh_trap_count!=1 || rh_trap_cause!=5 || rh_trap_tval!=0 ||
      rh_trap_epc!=(uintptr_t)rh_qbs_site || qbs_commands!=6 || akv_commands!=65 ||
      rows_checked!=62 || words_checked!=192) return fail("final_contract");
  printf("READER_HANDOFF_PASS qbs=6 akv=65 traps=1 cause=5 tval=0 qbs_words=192 akv_rows=62 context_test=1 performance=not_measured\n");
  return 0;
}
