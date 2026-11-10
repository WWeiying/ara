#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "printf.h"
#include "qk_data.h"

typedef struct {
  uint64_t before_fcsr, before_vstart, traps, cause, pc, mtval;
  uint64_t trap_fcsr, trap_vstart, after_fcsr, after_vstart, unexpected;
  uint64_t armed, expected_pc, resume_pc;
  uint64_t before_mstatus, trap_mstatus, after_mstatus;
  uint64_t before_vl, before_vtype, after_vl, after_vtype, trap_csrs_valid;
} observation_t;
volatile observation_t boundary_observation;
uint32_t boundary_dest_capture[384] __attribute__((aligned(64)));
_Static_assert(offsetof(observation_t, armed) == 88 &&
               offsetof(observation_t, resume_pc) == 104 &&
               offsetof(observation_t, trap_csrs_valid) == 168, "Frozen trap ABI");
extern void boundary_fill(const akv_descriptor_t *, uint64_t), boundary_release(void);
extern void qk_dest_set(const uint32_t *);
extern uint64_t qk_issue(uint64_t, uint64_t, uint64_t, uint64_t, uint32_t *, uint64_t, uint64_t, uint64_t);
extern uint64_t qk_pv_once(const uint16_t *, uint16_t *);
extern uint64_t qk_helper_observe(float *, uint32_t, uint32_t, uint32_t, uint32_t);
extern unsigned boundary_compat(void);
static struct { uint64_t before[8]; uint32_t data[128]; uint64_t after[8]; }
    output __attribute__((aligned(64)));
static const uint16_t pv_source[384] __attribute__((aligned(64))) = {
  [0 ... 127]=0x3c00, [128 ... 255]=0x7c01, [256]=0x3800, [257 ... 383]=0x7c01};
static uint16_t pv_output[64] __attribute__((aligned(64)));
static unsigned errors, successes, rejected;

static void csr(uint64_t flags) {
  __asm__ volatile("csrw fcsr,%0\ncsrwi vstart,0\ncsrwi vcsr,0" : : "r"(flags) : "memory");
}
static void fill(const qk_case_t *c) {
  akv_descriptor_t d = {0};
  d.version = AKV_DESCRIPTOR_VERSION; d.element_format = AKV_ELEMENT_FORMAT_F16;
  d.q_rows = c->context_queries; d.head_dim = c->context_dimension; d.kv_length = c->context_tokens;
  d.q_row_stride_bytes = d.k_token_stride_bytes = d.v_token_stride_bytes = 256;
  d.q_base = (uintptr_t)c->query; d.k_base = (uintptr_t)c->key; d.v_base = (uintptr_t)qk_values;
  if (!akv_v2_descriptor_is_valid(&d)) { errors++; return; }
  boundary_fill(&d, 0);
}
static unsigned guards(unsigned t, unsigned h, unsigned bad) {
  unsigned n = 0;
  for (unsigned i=0;i<8;i++) n += output.before[i] != UINT64_C(0xa5a5a5a5a5a5a5a5) ||
                                  output.after[i] != UINT64_C(0xa5a5a5a5a5a5a5a5);
  for (unsigned head=0;head<2;head++)
    for (unsigned i=(bad || head>=h) ? 0:t;i<64;i++) n += output.data[head*64+i] != 0xa5a5a5a5u;
  return n;
}
static void attempt(const qk_case_t *c, unsigned bad) {
  memset((void *)&boundary_observation,0,sizeof(boundary_observation));
  memset(&output,0xa5,sizeof(output));
  csr((c->rm<<5)|c->initial_flags);
  qk_dest_set(qk_destination);
  const uint64_t rm = bad && c->kind==KIND_FRM ? 5:c->rm;
  const uint64_t start = bad && c->kind==KIND_VSTART ? 1:0;
  const uint64_t control = bad ? c->bad_control:c->control;
  qk_issue(control,rm,start,bad,output.data,c->tokens,c->heads,bad ? c->bad_mode:c->mode);
  const observation_t o = *(const volatile observation_t *)&boundary_observation;
  const unsigned g = guards(c->tokens,c->heads,bad);
  errors += g+o.unexpected+(o.traps!=bad);
  errors += o.before_fcsr != ((rm<<5)|c->initial_flags) || o.before_vstart!=start;
  errors += o.before_vl!=o.after_vl || o.before_vtype!=o.after_vtype;
  if (bad) {
    rejected++;
    const unsigned off = c->kind==KIND_FS_OFF || c->kind==KIND_VS_OFF;
    errors += o.cause!=2 || o.pc!=o.expected_pc || o.armed!=0 || o.trap_csrs_valid!=!off;
    if (off) {
      const uint64_t mask=c->kind==KIND_FS_OFF ? 0x6000:0x600;
      errors += ((o.before_mstatus|o.trap_mstatus|o.after_mstatus)&mask)!=0;
    } else errors += o.trap_fcsr!=o.before_fcsr || o.trap_vstart!=start;
    errors += o.after_fcsr!=o.before_fcsr || o.after_vstart!=start;
    for (unsigned i=0;i<384;i++) errors += boundary_dest_capture[i]!=qk_destination[i];
  } else {
    successes++;
    errors += o.after_fcsr!=c->expected_fcsr || o.after_vstart!=0;
    for (unsigned h=0;h<c->heads;h++) for (unsigned t=0;t<c->tokens;t++)
      errors += output.data[h*64+t]!=c->expected[h*c->tokens+t];
  }
  printf("QK_BOUNDARY_CASE id=%lu phase=%u d=%lu heads=%lu tokens=%lu base=%lu rm=%lu before_fcsr=%lu before_vstart=%lu after_fcsr=%lu after_vstart=%lu traps=%lu cause=%lu pc=%016lx mtval=%016lx trap_fcsr=%lu trap_vstart=%lu unexpected=%lu guard_errors=%u before_mstatus=%016lx trap_mstatus=%016lx after_mstatus=%016lx before_vl=%lu before_vtype=%016lx after_vl=%lu after_vtype=%016lx trap_csrs_valid=%lu\n",
    c->id,!bad,c->dimension,c->heads,c->tokens,(control>>9)&7,c->rm,o.before_fcsr,o.before_vstart,
    o.after_fcsr,o.after_vstart,o.traps,o.cause,o.pc,o.mtval,o.trap_fcsr,o.trap_vstart,o.unexpected,g,
    o.before_mstatus,o.trap_mstatus,o.after_mstatus,o.before_vl,o.before_vtype,o.after_vl,o.after_vtype,o.trap_csrs_valid);
  printf("QK_BOUNDARY_DATA id=%lu phase=%u kind=%s bits=",c->id,!bad,bad ? "dest32":"result");
  if (bad) for (unsigned i=0;i<384;i++) printf("%08x",boundary_dest_capture[i]);
  else for (unsigned h=0;h<c->heads;h++) for (unsigned t=0;t<c->tokens;t++) printf("%08x",output.data[h*64+t]);
  printf("\n");
}
static void pv(unsigned id) {
  csr(0);
  const uint64_t f=qk_pv_once(pv_source,pv_output);
  errors += f!=0;
  printf("QK_BOUNDARY_PV id=%u fcsr=%lu bits=",id,f);
  for (unsigned i=0;i<64;i++) { errors += pv_output[i]!=0x3e00; printf("%04x",(unsigned)pv_output[i]); }
  printf("\n");
}
static void helper(const qk_case_t *c) {
  memset(&output,0xa5,sizeof(output));
  csr(0);
  const uint64_t f=qk_helper_observe((float *)output.data,c->tokens,c->heads,c->dimension,c->query_base);
  const unsigned g=guards(c->tokens,c->heads,0);
  errors += g+(f!=c->qk_flags);
  for (unsigned h=0;h<c->heads;h++) for (unsigned t=0;t<c->tokens;t++)
    errors += output.data[h*64+t]!=c->expected[h*c->tokens+t];
  successes++;
  printf("QK_BOUNDARY_HELPER id=0 fcsr=%lu guard_errors=%u bits=",f,g);
  for (unsigned h=0;h<c->heads;h++) for (unsigned t=0;t<c->tokens;t++) printf("%08x",output.data[h*64+t]);
  printf("\n");
}
int main(void) {
  uint64_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  printf("QK_BOUNDARY_BEGIN cases=23 vlenb=%lu data=%s\n",vlenb,QK_DATA_SHA256);
  if (vlenb!=128) return 1;
  for (unsigned i=0;i<QK_CASES;i++) {
    const qk_case_t *c=&qk_cases[i];
    csr(0); fill(c);
    if (i==0) pv(0);
    if (c->rejection) {
      if (c->kind==KIND_NO_CONTEXT) boundary_release();
      attempt(c,1);
      if (c->kind==KIND_NO_CONTEXT) fill(c);
      qk_case_t r=*c;
      r.dimension=c->recovery_dimension; r.tokens=c->recovery_tokens;
      r.control=c->recovery_control; r.qk_flags=c->recovery_flags; r.expected=c->recovery_expected;
      r.query_base=(r.control>>9)&7;
      r.expected_fcsr=(r.rm<<5)|r.initial_flags|r.qk_flags; r.mode=0;
      attempt(&r,0);
    } else attempt(c,0);
    if (i==0) { helper(c); pv(1); }
    boundary_release();
  }
  errors += boundary_compat();
  printf("QK_BOUNDARY_DONE cases=23 successes=%u rejected=%u helper=1 pv=2 compat=1 errors=%u\n",successes,rejected,errors);
  return errors!=0;
}
