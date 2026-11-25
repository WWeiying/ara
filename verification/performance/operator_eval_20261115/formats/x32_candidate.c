/* New multi-output candidates for formats absent from the archived x32 set.
   Each vector lane is an output column, not an element of a single dot. */
#include <stdint.h>
#include <string.h>
#include <math.h>
#ifdef __riscv_vector
#include <riscv_vector.h>
#endif

static const int8_t iq4[16]={-127,-104,-83,-65,-49,-35,-22,-10,1,13,25,38,53,69,89,113};
#ifndef __riscv_vector
static float half_float(const unsigned char *p) {
  uint16_t h; memcpy(&h,p,2);
  unsigned exp=(h>>10)&31, mantissa=h&1023;
  float f=exp ? ldexpf((float)(1024+mantissa),(int)exp-25) : ldexpf((float)mantissa,-24);
  return h&32768 ? -f : f;
}
static void scalar(unsigned profile, const unsigned char *w, const unsigned char *a,
                   float *out, unsigned k) {
  unsigned be=profile==7 ? 256 : 32, wb=profile==7 ? 84 : profile==8 ? 22 : 18;
  unsigned ab=profile==7 ? 292 : 34;
  for (unsigned col=0;col<32;++col) {
    float sum=0;
    for (unsigned b=0;b<k/be;++b) {
      const unsigned char *p=w+b*32*wb, *act=a+b*ab;
      float ad;
      if (profile==7) memcpy(&ad,act,4); else ad=half_float(act);
      int dot=0, correction=0;
      for (unsigned e=0;e<be;++e) {
        int q;
        if (profile==7) {
          unsigned group=(e%128)/16, byte=(e/128)*32+(group&1)*16+e%16;
          q=(p[4*32+16*32+byte*32+col]>>(2*(group/2)))&3;
          unsigned scale=p[4*32+(e/16)*32+col];
          int av=(int8_t)act[4+e];
          dot+=(scale&15)*q*av;
          correction+=(scale>>4)*av;
        } else {
          unsigned offset=profile==8 ? 6 : 2;
          q=(p[offset*32+(e%16)*32+col]>>(e<16 ? 0 : 4))&15;
          if (profile==8) q=(q|(((p[2*32+(e/8)*32+col]>>(e%8))&1)<<4))-16;
          else if (profile==9) q=iq4[q]; else q-=8;
          dot+=q*(int8_t)act[2+e];
        }
      }
      sum=fmaf(ad*half_float(p+col*2),(float)dot,sum);
      if (profile==7) sum-=ad*half_float(p+2*32+col*2)*(float)correction;
    }
    out[col]=sum;
  }
}
#else
static inline vfloat32m1_t scales(const unsigned char *p, size_t vl) {
  return __riscv_vfwcvt_f_f_v_f32m1(__riscv_vle16_v_f16mf2((const _Float16 *)p,vl),vl);
}
static inline vint16mf2_t extend(vuint8mf4_t v, size_t vl) {
  return __riscv_vreinterpret_v_u16mf2_i16mf2(__riscv_vzext_vf2_u16mf2(v,vl));
}
static inline void vector(unsigned profile, const unsigned char *w, const unsigned char *a,
                          float *out, unsigned k) {
  unsigned be=profile==7 ? 256 : 32, wb=profile==7 ? 84 : profile==8 ? 22 : 18;
  unsigned ab=profile==7 ? 292 : 34;
  const size_t vl=__riscv_vsetvl_e32m1(32);
  vfloat32m1_t sum=__riscv_vfmv_v_f_f32m1(0,vl);
  for (unsigned b=0;b<k/be;++b) {
    const unsigned char *p=w+b*32*wb, *act=a+b*ab;
    vint32m1_t dot=__riscv_vmv_v_x_i32m1(0,vl), correction=dot;
    float ad;
    if (profile==7) {
      memcpy(&ad,act,4);
      for (unsigned group=0;group<16;++group) {
        vuint8mf4_t sc=__riscv_vle8_v_u8mf4(p+4*32+group*32,vl);
        vint16mf2_t scale=extend(__riscv_vand_vx_u8mf4(sc,15,vl),vl);
        vint16mf2_t min=extend(__riscv_vsrl_vx_u8mf4(sc,4,vl),vl);
        vint16mf2_t partial=__riscv_vmv_v_x_i16mf2(0,vl);
        int bsum=0;
        for (unsigned i=0;i<16;++i) {
          unsigned byte=(group/8)*32+(group&1)*16+i;
          vuint8mf4_t q=__riscv_vle8_v_u8mf4(p+20*32+byte*32,vl);
          q=__riscv_vand_vx_u8mf4(__riscv_vsrl_vx_u8mf4(q,2*((group%8)/2),vl),3,vl);
          int av=(int8_t)act[4+group*16+i]; bsum+=av;
          partial=__riscv_vwmacc_vx_i16mf2(partial,av,__riscv_vreinterpret_v_u8mf4_i8mf4(q),vl);
        }
        dot=__riscv_vwmacc_vv_i32m1(dot,scale,partial,vl);
        correction=__riscv_vwmacc_vx_i32m1(correction,bsum,min,vl);
      }
    } else {
      _Float16 ah; memcpy(&ah,act,2); ad=(float)ah;
      for (unsigned e=0;e<32;++e) {
        unsigned offset=profile==8 ? 6 : 2;
        vuint8mf4_t q=__riscv_vle8_v_u8mf4(p+offset*32+(e%16)*32,vl);
        q=__riscv_vand_vx_u8mf4(__riscv_vsrl_vx_u8mf4(q,e<16 ? 0 : 4,vl),15,vl);
        vint16mf2_t v;
        if (profile==8) {
          vuint8mf4_t high=__riscv_vle8_v_u8mf4(p+2*32+(e/8)*32,vl);
          high=__riscv_vsll_vx_u8mf4(__riscv_vand_vx_u8mf4(__riscv_vsrl_vx_u8mf4(high,e%8,vl),1,vl),4,vl);
          v=__riscv_vsub_vx_i16mf2(extend(__riscv_vor_vv_u8mf4(q,high,vl),vl),16,vl);
        } else if (profile==9) {
          vint8mf4_t lookup=__riscv_vloxei8_v_i8mf4(iq4,q,vl);
          v=__riscv_vsext_vf2_i16mf2(lookup,vl);
        } else v=__riscv_vsub_vx_i16mf2(extend(q,vl),8,vl);
        dot=__riscv_vwmacc_vx_i32m1(dot,(int8_t)act[2+e],v,vl);
      }
    }
    vfloat32m1_t d=__riscv_vfmul_vf_f32m1(scales(p,vl),ad,vl);
    sum=__riscv_vfmacc_vv_f32m1(sum,__riscv_vfcvt_f_x_v_f32m1(dot,vl),d,vl);
    if (profile==7) {
      vfloat32m1_t dm=__riscv_vfmul_vf_f32m1(scales(p+2*32,vl),ad,vl);
      vfloat32m1_t corr=__riscv_vfmul_vv_f32m1(__riscv_vfcvt_f_x_v_f32m1(correction,vl),dm,vl);
      sum=__riscv_vfsub_vv_f32m1(sum,corr,vl);
    }
  }
  __riscv_vse32_v_f32m1(out,sum,vl);
}
#endif

#ifdef __riscv_vector
#define EXEC vector
#else
#define EXEC scalar
#endif
#define KERNEL(name,p) \
void name(const void *w,const void *a,float *out,unsigned k) { EXEC(p,w,a,out,k); }
KERNEL(formats_q2k_x32,7)
KERNEL(formats_q4_0_x32,3)
KERNEL(formats_q5_0_x32,8)
KERNEL(formats_iq4nl_x32,9)
