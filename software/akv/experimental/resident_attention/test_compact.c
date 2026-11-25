/* Actual RVV execution; no AKV custom arithmetic is substituted as a PASS. */
#include "akv/akv.h"
#include "akv/akv_features.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <riscv_vector.h>
#ifndef PREP_ONLY
#include <stdio.h>
#include <sys/reboot.h>
#include <unistd.h>
#endif
#include "captures.h"

extern void old_softmax(const uint16_t *, float, akv_attention_v2_workspace_t *,
                        uint32_t, uint32_t, uint32_t);
extern void new_softmax(const uint16_t *, float, akv_attention_v2_workspace_t *,
                        uint32_t, uint32_t, uint32_t, unsigned);
extern void old_layout(size_t *);
extern void new_layout(size_t *);
extern void capture_old(const float *, const uint16_t *, const float *,
                        uint32_t, uint32_t, uint32_t, uint64_t, uint16_t *);
extern void capture_new(const uint16_t *, const uint16_t *, const float *,
                        uint32_t, uint32_t, uint32_t, uint64_t, uint16_t *);

_Static_assert(sizeof(((akv_attention_v2_workspace_t *)0)->score[0]) == 256, "F32 row ABI");
_Static_assert(sizeof(((akv_attention_v2_workspace_t *)0)->resident_probability[0]) == 256, "F16 row ABI");
_Static_assert(offsetof(akv_attention_v2_workspace_t, score) ==
               offsetof(akv_attention_v2_workspace_t, resident_probability), "scratch alias");

static inline unsigned fcsr(void) {
  unsigned v; __asm__ volatile("frcsr %0" : "=r"(v) : : "memory"); return v;
}
static inline void set_fcsr(unsigned v) {
  __asm__ volatile("fscsr %0" : : "r"(v) : "memory");
}
static uint32_t bits(float v) { uint32_t x; memcpy(&x, &v, 4); return x; }
static float value(uint32_t x) { float v; memcpy(&v, &x, 4); return v; }
static void narrow_row(uint16_t *to, const float *from, unsigned t) {
  size_t vl = __riscv_vsetvl_e32m2(t);
  vfloat32m2_t v = __riscv_vle32_v_f32m2(from, vl);
  __riscv_vse16_v_u16m1(to, __riscv_vreinterpret_v_f16m1_u16m1(
      __riscv_vfncvt_f_f_w_f16m1(v, vl)), vl);
}

static uint32_t prep_cases, softmax_cases;
/* a7 points at 384 halfwords plus one control word. Untouched redzones follow. */
static uint16_t old_source[400] __attribute__((aligned(64)));
static uint16_t new_source[400] __attribute__((aligned(64)));
static uint16_t compact[2][128] __attribute__((aligned(64)));
static float probability[2][64] __attribute__((aligned(64)));
static uint16_t seed[2][256] __attribute__((aligned(64)));
static float scale[2];

static int one_prep(unsigned t, unsigned d, unsigned h, unsigned csr) {
  for (unsigned i=0;i<400;++i) old_source[i]=new_source[i]=0x5a5a;
  for (unsigned i=0;i<256;++i) ((uint16_t *)compact)[i]=0x7d55;
  const uint64_t control=(t-1u)|((h-1u)<<6)|((d==64?0u:d==96?2u:1u)<<7);
  set_fcsr(csr);
  capture_old(&probability[0][0], &seed[0][0], scale, t, d, h, control, old_source);
  const unsigned old_flags=fcsr();
  set_fcsr(csr);
  for (unsigned head=0;head<h;++head) narrow_row(compact[head],probability[head],t);
  capture_new(&compact[0][0], &seed[0][0], scale, t, d, h, control, new_source);
  if (old_flags!=fcsr()) return 10;
  for (unsigned head=0;head<h;++head)
    for (unsigned i=0;i<d;++i)
      if (old_source[128*head+i]!=new_source[128*head+i]) return 11;
  for (unsigned i=0;i<t;++i)
    for (unsigned head=0;head<2;++head)
      if (old_source[256+2*i+head]!=new_source[256+2*i+head]) return 12;
  uint64_t old_control,new_control;
  memcpy(&old_control,old_source+384,8); memcpy(&new_control,new_source+384,8);
  if (old_control!=control || new_control!=control) return 13;
  for (unsigned i=388;i<400;++i)
    if (old_source[i]!=0x5a5a || new_source[i]!=0x5a5a) return 14;
  for (unsigned head=0;head<2;++head)
    for (unsigned i=head<h?t:0;i<128;++i)
      if (compact[head][i]!=0x7d55) return 15;
  ++prep_cases;
  return 0;
}

static int preparation(void) {
  const uint32_t samples[]={0,0x80000000,0x3f800000,0xbf800000,0x33800000,
    0x33000000,0x38800000,0x387fffff,0x477fe000,0x47800000,0x7f800000,
    0xff800000,0x7fc12345,0x7f812345,1,0x3f801000};
  const uint16_t halves[]={0,0x8000,0x3c00,0xbc00,1,0x03ff,0x0400,0x7bff,
    0x7c00,0xfc00,0x7e55,0x7d55};
  for(unsigned pattern=0;pattern<4;++pattern) {
    for(unsigned h=0;h<2;++h) {
      scale[h]=value(samples[(pattern*3+h*7)%16]);
      for(unsigned i=0;i<64;++i) probability[h][i]=value(samples[(i+pattern+h*3)%16]);
      for(unsigned i=0;i<256;++i) seed[h][i]=halves[(i+pattern*3+h)%12];
    }
    for(unsigned t=1;t<=64;++t)
      for(unsigned d=64;d<=128;d+=32)
        for(unsigned h=1;h<=2;++h) {
          int rc=one_prep(t,d,h,pattern&1?17:0); if(rc) return rc;
        }
    for(unsigned rm=1;rm<5;++rm)
      for(unsigned t=1;t<=64;t+=21)
        for(unsigned h=1;h<=2;++h) {
          int rc=one_prep(t,128,h,rm<<5); if(rc) return rc;
        }
  }
  /* The three real Qwen3 probability/seed/scale snapshots from VCS. */
  for(unsigned c=0;c<3;++c) {
    memcpy(probability,capture_probability[c],sizeof(probability));
    memcpy(scale,capture_scale[c],sizeof(scale));
    for(unsigned h=0;h<2;++h)
      memcpy(seed[h],capture_seed[c]+128*h,256);
    for(unsigned sticky=0;sticky<=1;++sticky) {
      int rc=one_prep(c==2?9:64,128,2,sticky?31:0); if(rc) return rc;
    }
  }
  /* Isolate narrowing flags: seed scaling is exact and cannot hide them. */
  const uint32_t isolated[]={0,0x3f800000,0x3eaaaaab,0x33000000,
                             0x47800000,0x7fc12345,0x7f812345};
  for(unsigned p=0;p<7;++p) {
    for(unsigned h=0;h<2;++h) {
      scale[h]=1.0f;
      for(unsigned i=0;i<256;++i) seed[h][i]=0x3c00;
      for(unsigned i=0;i<64;++i) probability[h][i]=value(isolated[p]);
    }
    for(unsigned t=1;t<=64;t+=63)
      for(unsigned d=64;d<=128;d+=32)
        for(unsigned h=1;h<=2;++h)
          for(unsigned sticky=0;sticky<2;++sticky) {
            int rc=one_prep(t,d,h,sticky?17:0); if(rc) return rc;
          }
  }
  return 0;
}

#ifndef PREP_ONLY
static akv_attention_v2_workspace_t initial,old_ws,new_ws,native_ws,before_ws;
static uint16_t mask[192] __attribute__((aligned(64)));
static int softmax(void) {
  size_t a[7],b[7]; old_layout(a); new_layout(b);
  if(memcmp(a,b,sizeof(a))) return 20;
  for(unsigned heads=1;heads<=AKV_MAX_Q_ROWS;++heads)
    for(unsigned tokens=1;tokens<=64;++tokens)
      for(unsigned pattern=0;pattern<6;++pattern) {
        memset(&initial,0xa5,sizeof(initial));
        for(unsigned i=0;i<192;++i)
          mask[i]=(pattern==1 || (pattern==2 && i%3==0))?0xfc00:0;
        for(unsigned head=0;head<heads;++head) {
          initial.maximum[head]=pattern<3?value(0xff800000):2.0f;
          initial.sum[head]=pattern<3?0.0f:1.5f;
          initial.old_scale[head]=0.0f;
          for(unsigned i=0;i<64;++i)
            initial.score[head][i]=pattern==4?-1000.0f:
              (float)((int)((i*17+head*13)%161)-80)*0.25f;
        }
        /* Three tiles reuse the same workspace, including fully masked first tiles. */
        old_ws=initial; new_ws=initial; native_ws=initial;
        for(unsigned tile=0;tile<3;++tile) {
          if(tile) {
            for(unsigned h=0;h<heads;++h)
              for(unsigned i=0;i<tokens;++i)
                old_ws.score[h][i]=new_ws.score[h][i]=native_ws.score[h][i]=
                  initial.score[h][i]+(float)tile;
          }
          unsigned csr=pattern&1?17:0;
          set_fcsr(csr);
          old_softmax(mask,0.125f,&old_ws,64*tile,tokens,heads);
          unsigned old_flags=fcsr();
          set_fcsr(csr);
          new_softmax(mask,0.125f,&native_ws,64*tile,tokens,heads,0);
          if(fcsr()!=old_flags || memcmp(&old_ws,&native_ws,sizeof(old_ws))) return 21;
          set_fcsr(old_flags);
          for(unsigned h=0;h<heads;++h) narrow_row(compact[0],old_ws.score[h],tokens);
          old_flags=fcsr();
          before_ws=new_ws;
          set_fcsr(csr);
          new_softmax(mask,0.125f,&new_ws,64*tile,tokens,heads,1);
          if(fcsr()!=old_flags) return 22;
          for(unsigned h=0;h<heads;++h) {
            narrow_row(compact[0],old_ws.score[h],tokens);
            if(memcmp(compact[0],new_ws.resident_probability[h],2*tokens)) return 23;
            if(bits(old_ws.maximum[h])!=bits(new_ws.maximum[h]) ||
               bits(old_ws.sum[h])!=bits(new_ws.sum[h]) ||
               bits(old_ws.old_scale[h])!=bits(new_ws.old_scale[h])) return 24;
          }
          if(memcmp(old_ws.accumulator,new_ws.accumulator,sizeof(old_ws.accumulator))) return 25;
          for(unsigned h=0;h<AKV_MAX_Q_ROWS;++h) {
            unsigned start=h<heads?tokens:0;
            if(memcmp(new_ws.resident_probability[h]+start,
                      before_ws.resident_probability[h]+start,256-2*start)) return 26;
          }
          ++softmax_cases;
        }
      }
  return 0;
}
#endif

int main(void) {
  int rc=preparation();
#ifndef PREP_ONLY
  if(!rc) rc=softmax();
  printf("COMPACT_CHECK rc=%d prep=%u softmax=%u custom_compute=0\n",rc,prep_cases,softmax_cases);
  fflush(stdout);
  reboot(RB_POWER_OFF);
#endif
  return rc;
}
