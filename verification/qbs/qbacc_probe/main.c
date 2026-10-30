#include <stddef.h>
#include <stdint.h>
#include "printf.h"
#include "qbs_abi.h"

typedef struct { uint16_t d; int8_t qs[32]; } block_q8_t;
_Static_assert(sizeof(block_q8_t)==34,"Q8_0 layout");
static block_q8_t weights[32] __attribute__((aligned(64)));
static block_q8_t activations[8] __attribute__((aligned(64)));
static qbs_descriptor_t descriptor;
static uint32_t seed[256] __attribute__((aligned(64)));
static uint32_t observed[256] __attribute__((aligned(64)));
static uint64_t status[6] __attribute__((aligned(64)));
static volatile uint64_t trap_count,trap_cause;

void __attribute__((naked,used,aligned(4))) mtvec_handler(void) {
  asm volatile("csrr t0, mcause\nla t1, trap_cause\nsd t0, 0(t1)\n"
               "la t1, trap_count\nld t0, 0(t1)\naddi t0, t0, 1\nsd t0, 0(t1)\n"
               "csrr t0, mepc\naddi t0, t0, 4\ncsrw mepc, t0\nmret\n");
}
void rvtest_init(void) { asm volatile("csrw mtvec, %0"::"r"(mtvec_handler):"memory"); }

typedef void (*probe_t)(const qbs_descriptor_t *,const block_q8_t *,const uint32_t *,uint32_t *,uint64_t *);
#define DECL(M) \
  extern void qbacc_m##M##_e8(const qbs_descriptor_t *,const block_q8_t *,const uint32_t *,uint32_t *,uint64_t *); \
  extern void qbacc_m##M##_e32(const qbs_descriptor_t *,const block_q8_t *,const uint32_t *,uint32_t *,uint64_t *);
DECL(1) DECL(3) DECL(4) DECL(5) DECL(8)

static uint32_t bits_of_uint(unsigned value) {
  union { float f; uint32_t u; } x;
  x.f=(float)value;
  return x.u;
}
static uint64_t info(uint64_t index) {
  register uint64_t a0 asm("a0")=index;
  asm volatile(".word 0x0005155b":"+r"(a0)::"memory");
  return a0;
}

static int run(unsigned m,unsigned n,unsigned regs,probe_t fn,unsigned invalid,unsigned ordinal) {
  const qbs_descriptor_fields_t fields={
    .descriptor_version=invalid ? QBS_DESCRIPTOR_VERSION+1:QBS_DESCRIPTOR_VERSION,
    .weight_profile=QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
    .activation_profile=QBS_ACTIVATION_PROFILE_Q8_0,
    .weight_layout=QBS_WEIGHT_LAYOUT_ROW_MAJOR,
    .activation_layout=m>4 ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED:
                       m==4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED:QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
    .n=(uint8_t)n,.k_blocks=1
  };
  descriptor.header=qbs_pack_descriptor_header(&fields);
  descriptor.weight_base=(uint64_t)(uintptr_t)weights;
  if (m>=4) {
    const unsigned rows=m>4 ? 8:4;
    uint8_t *packed=(uint8_t *)activations;
    for (unsigned r=0;r<rows;r++) { packed[2*r]=0; packed[2*r+1]=0x3c; }
    for (unsigned q=0;q<32;q++)
      for (unsigned r=0;r<rows;r++) packed[2*rows+q*rows+r]=1;
  } else {
    for (unsigned r=0;r<8;r++) {
      activations[r].d=0x3c00;
      for (unsigned q=0;q<32;q++) activations[r].qs[q]=1;
    }
  }
  for (unsigned i=0;i<256;i++) { seed[i]=bits_of_uint(i+1); observed[i]=UINT32_C(0xdeadbeef); }
  const uint64_t before=trap_count;
  fn(&descriptor,activations,seed,observed,status);
  if (trap_count-before!=invalid || (invalid && trap_cause!=2)) {
    printf("QBACC_TRAP_FAIL ordinal=%u delta=%lu cause=%lu\n",ordinal,
           (unsigned long)(trap_count-before),(unsigned long)trap_cause);
    return 1;
  }
  for (unsigned i=0;i<regs*32;i++) {
    const unsigned active=i/32<m && i%32<n && !invalid;
    // Match existing QBS commit: narrow-M row tails are zeroed, wide-M
    // tails and LMUL padding retain old register bytes. Faults write nothing.
    const unsigned zero_tail=!invalid && m<=4 && i/32<m && i%32>=n;
    const uint32_t want=zero_tail ? 0:bits_of_uint(i+1+(active ? 32:0));
    if (observed[i]!=want) {
      printf("QBACC_DATA_FAIL ordinal=%u m=%u n=%u index=%u got=%08x expected=%08x\n",
             ordinal,m,n,i,observed[i],want);
      return 1;
    }
  }
  if (status[0]!=7 || status[0]!=status[2] || status[1]!=status[3] || status[4]!=8 || status[5]!=5) {
    printf("QBACC_STATUS_FAIL ordinal=%u vl=%lu/%lu vtype=%lx/%lx fcsr=%lu vcsr=%lu\n",
           ordinal,(unsigned long)status[0],(unsigned long)status[2],
           (unsigned long)status[1],(unsigned long)status[3],
           (unsigned long)status[4],(unsigned long)status[5]);
    return 1;
  }
  return 0;
}

int main(void) {
  if (info(QBS_VRF_CONTINUATION_CAPABILITY_INDEX)!=1) { printf("QBACC_CAPABILITY_FAIL\n"); return 1; }
  for (unsigned i=0;i<32;i++) { weights[i].d=0x3c00; for (unsigned q=0;q<32;q++) weights[i].qs[q]=1; }
  struct { unsigned m,n,regs; probe_t plain,mixed; } cases[]={
    {1,1,1,qbacc_m1_e32,qbacc_m1_e8}, {3,17,4,qbacc_m3_e32,qbacc_m3_e8},
    {4,32,4,qbacc_m4_e32,qbacc_m4_e8}, {5,7,8,qbacc_m5_e32,qbacc_m5_e8},
    {8,15,8,qbacc_m8_e32,qbacc_m8_e8}, {8,16,8,qbacc_m8_e32,qbacc_m8_e8}
  };
  unsigned ordinal=0;
  for (unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
    if (run(cases[i].m,cases[i].n,cases[i].regs,cases[i].plain,0,ordinal++)) return 1;
    if (run(cases[i].m,cases[i].n,cases[i].regs,cases[i].mixed,0,ordinal++)) return 1;
  }
  if (run(4,7,4,qbacc_m4_e8,1,ordinal++)) return 1;
  printf("QBACC_SOC_PASS cases=%u computed=12 validation_faults=1 csr_preserved=1 tail_policy_checked=1 padding_preserved=1\n",ordinal);
  return 0;
}
