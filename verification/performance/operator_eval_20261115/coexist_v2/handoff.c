/* Read-only archived handoff input and issue helpers, with guard-only source
 * adaptation recorded by prepare.py. Its skip-capable main is never called. */
#define main archived_handoff_main
#include "archived_handoff.c"
#undef main
#include <string.h>
#include "handoff_expected.h"

static struct __attribute__((aligned(64))) {
  unsigned char before[64]; float value[2][64]; unsigned char after[64];
} scores;
static struct __attribute__((aligned(64))) {
  unsigned char before[64]; uint16_t value[2][256]; unsigned char after[64];
} seeds;
static const float probabilities[2][64] __attribute__((aligned(64))) = {
  {[0 ... 2]=1.0f}, {[0 ... 2]=1.0f}
};
static const float scales[2] __attribute__((aligned(64))) = {1.0f,1.0f};
static const uint32_t fa[16] __attribute__((aligned(64))) = {[0 ... 15]=0x3f800000};
static const uint32_t fb[16] __attribute__((aligned(64))) = {[0 ... 15]=0x40000000};
static const uint32_t fc[16] __attribute__((aligned(64))) = {[0 ... 15]=0x40400000};
static const uint32_t ia[16] __attribute__((aligned(64))) = {[0 ... 15]=0x80000003};
static const uint32_t ib[16] __attribute__((aligned(64))) = {[0 ... 15]=0x7ffffffd};
static uint64_t input_hash;
extern void akv_experimental_resident_qk(float *,unsigned,unsigned,unsigned,unsigned);
extern void akv_experimental_resident_pv(const float *,uint16_t *,const float *,unsigned,unsigned,unsigned);

static uint64_t fingerprint(void) {
  const void *p[]={qbs_weights,&qbs_activation,akv_query,akv_key,akv_value,probabilities,scales,fa,fb,fc,ia,ib,
                  &qbs_descriptor,&akv_descriptor};
  const size_t n[]={sizeof(qbs_weights),sizeof(qbs_activation),sizeof(akv_query),sizeof(akv_key),
    sizeof(akv_value),sizeof(probabilities),sizeof(scales),sizeof(fa),sizeof(fb),sizeof(fc),sizeof(ia),sizeof(ib),
    sizeof(qbs_descriptor),sizeof(akv_descriptor)};
  uint64_t h=UINT64_C(14695981039346656037);
  for (unsigned i=0;i<sizeof(p)/sizeof(p[0]);++i)
    for (size_t j=0;j<n[i];++j) h=(h^((const unsigned char *)p[i])[j])*UINT64_C(1099511628211);
  return h;
}
static int a5(const unsigned char *p,size_t size) {
  for (size_t i=0;i<size;++i) if (p[i]!=0xa5) return 1;
  return 0;
}
static void detail(uint64_t *p) {
  __asm__ volatile("csrr %0,vl\ncsrr %1,vtype\ncsrr %2,vstart"
      :"=r"(p[0]),"=r"(p[1]),"=r"(p[2])::"memory");
}
static void sync_v8(void) {
  uintptr_t x;__asm__ volatile("vmv.x.s %0,v8\nfence rw,rw":"=r"(x)::"memory");
}
static void sync_v0(void) {
  uintptr_t x;__asm__ volatile("vmv.x.s %0,v0\nfence rw,rw":"=r"(x)::"memory");
}
int co_platform_prepare(void) {
  initialize_descriptors();
  memset(&scores,0xa5,sizeof(scores));memset(&seeds,0xa5,sizeof(seeds));
  memset(&co_guard_qbs,0xa5,sizeof(co_guard_qbs));
  memset(&co_guard_akv,0xa5,sizeof(co_guard_akv));
  memset(&co_guard_rvv_source,0xa5,sizeof(co_guard_rvv_source));
  memset(&co_guard_rvv_observed,0xa5,sizeof(co_guard_rvv_observed));
  for (unsigned h=0;h<2;++h) for (unsigned d=0;d<64;++d) seeds.value[h][d]=0;
  const uint64_t q=issue_qbinfo(0),k=issue_akvinfo(2),r=issue_akvinfo(4);
  const uint64_t expected=akv_resident_qk_capability_word(4,1)|akv_resident_pv_capability_word(4,1);
  if (trap_count || q!=qbs_capability_word(0,VLEN) || k!=akv_v2_capability_word(2,1) || r!=expected)
    return 1;
  printf("CO_CAP qbs=%lx akv=%lx resident=%lx\n",q,k,r);
  input_hash=fingerprint();return 0;
}
int co_platform_check(void) {
  int errors=trap_count || input_hash!=fingerprint();
  errors+=a5(scores.before,64)+a5(scores.after,64)+a5(seeds.before,64)+a5(seeds.after,64);
  errors+=a5(co_guard_qbs.before,64)+a5(co_guard_qbs.after,64)+
      a5(co_guard_akv.before,64)+a5(co_guard_akv.after,64)+
      a5(co_guard_rvv_source.before,64)+a5(co_guard_rvv_source.after,64)+
      a5(co_guard_rvv_observed.before,64)+a5(co_guard_rvv_observed.after,64);
  for (unsigned h=0;h<2;++h) {
    errors+=a5((const unsigned char *)&scores.value[h][3],61*4);
    errors+=a5((const unsigned char *)&seeds.value[h][64],192*2);
    for (unsigned t=0;t<3;++t) {
      uint32_t bits;memcpy(&bits,&scores.value[h][t],4);
      errors+=bits!=handoff_qk_gold[h*3+t];
    }
    for (unsigned d=0;d<64;++d) errors+=seeds.value[h][d]!=handoff_pv_gold[h*64+d];
  }
  printf("CO_HANDOFF traps=%lu input_unchanged=%u errors=%u\n",trap_count,input_hash==fingerprint(),errors);
  return errors;
}
__attribute__((noinline,noclone)) void co_qbs(unsigned char *out,uint64_t *d) {
  issue_qbs_m1(1);sync_v8();detail(d);memcpy(out,qbs_observed,sizeof(qbs_observed));
}
__attribute__((noinline,noclone)) void co_rvv_mul(unsigned char *out,uint64_t *d) {
  __asm__ volatile("li t0,16\nvsetvli zero,t0,e32,m1,tu,mu\n"
      "vle32.v v8,(%0)\nvle32.v v16,(%1)\nvmul.vv v24,v8,v16\nvse32.v v24,(%2)"
      ::"r"(ia),"r"(ib),"r"(out):"t0","v8","v16","v24","memory");detail(d);
}
__attribute__((noinline,noclone)) void co_rvv_fma(unsigned char *out,uint64_t *d) {
  __asm__ volatile("li t0,16\nvsetvli zero,t0,e32,m1,tu,mu\n"
      "vle32.v v8,(%0)\nvle32.v v16,(%1)\nvle32.v v24,(%2)\n"
      "vfmacc.vv v24,v8,v16\nvse32.v v24,(%3)"
      ::"r"(fa),"r"(fb),"r"(fc),"r"(out):"t0","v8","v16","v24","memory");detail(d);
}
__attribute__((noinline,noclone)) void co_akv_begin(unsigned char *out,uint64_t *d) {
  issue_akv_v2_full();issue_akv_load_d64(akv_v2_selector(AKV_STREAM_K,2));
  sync_v8();detail(d);memcpy(out,akv_observed,sizeof(akv_observed));
}
__attribute__((noinline,noclone)) void co_resident_qk(unsigned char *out,uint64_t *d) {
  akv_experimental_resident_qk(&scores.value[0][0],3,2,64,0);sync_v0();detail(d);
  memcpy(out,scores.value[0],12);memcpy(out+12,scores.value[1],12);
}
__attribute__((noinline,noclone)) void co_resident_pv(unsigned char *out,uint64_t *d) {
  akv_experimental_resident_pv(&probabilities[0][0],&seeds.value[0][0],scales,3,64,2);
  sync_v0();detail(d);memcpy(out,seeds.value[0],128);memcpy(out+128,seeds.value[1],128);
}
__attribute__((noinline,noclone)) void co_akv_release(unsigned char *out,uint64_t *d) {
  issue_akv_release();detail(d);(void)out;
}
__attribute__((noinline,noclone)) void co_adjacent(unsigned char *out,uint64_t *d) {
  issue_qbs_m1(0);issue_akv_v2_full();
  issue_akv_load_d64(akv_v2_selector(AKV_STREAM_K,1));issue_akv_release();
  sync_v8();detail(d);memcpy(out,akv_observed,sizeof(akv_observed));
}
__attribute__((noinline,noclone)) void co_reverse(unsigned char *out,uint64_t *d) {
  issue_akv_v2_full();issue_akv_release();issue_qbs_m1(1);
  sync_v8();detail(d);memcpy(out,qbs_observed,sizeof(qbs_observed));
}
