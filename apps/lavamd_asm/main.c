// SPDX-License-Identifier: Apache-2.0
// Plain-Ara hand-asm baseline of a LavaMD-style N-body force kernel.
// Core of Rodinia LavaMD: force on a reference particle A from N neighbour
// particles B, with a Gaussian potential vij = exp(-a2 * r2).  Flat arrays,
// self-contained; the exp polynomial reuses the verified Cephes f32 sequence.
// Only lavamd_clean (the force loop) is the measured kernel; data prep and the
// scalar gold check live outside it.

#include <math.h>
#include <stdint.h>
#include <string.h>

#include "runtime.h"
#include "util.h"

#ifdef SPIKE
#include <stdio.h>
#elif defined ARA_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

#define CHECK
#define THRESHOLD 0.01
#define NPAR 256                     // multiple of VLMAX (=32 at VLEN=1024,e32)

extern float bx[];                   // defined in data.S
extern float by[];
extern float bz[];
extern float bv[];
extern float bq[];
extern float aparams[];              // av, ax, ay, az, a2
extern float fout_v[];               // fv, fx, fy, fz (vector kernel)
extern float fout_s[];               // gold

// ---- scalar gold reference ------------------------------------------------
static void lavamd_ref(const float *px, const float *py, const float *pz,
                       const float *pv, const float *pq, const float *ap,
                       float *fo, int n) {
  float av = ap[0], ax = ap[1], ay = ap[2], az = ap[3], a2 = ap[4];
  float fv = 0, fx = 0, fy = 0, fz = 0;
  for (int j = 0; j < n; ++j) {
    float dot = ax * px[j] + ay * py[j] + az * pz[j];
    float r2 = (av + pv[j]) - dot;
    float vij = expf(-(a2 * r2));
    float fs = 2.f * vij;
    float fxij = fs * (ax - px[j]);
    float fyij = fs * (ay - py[j]);
    float fzij = fs * (az - pz[j]);
    fv += pq[j] * vij;
    fx += pq[j] * fxij;
    fy += pq[j] * fyij;
    fz += pq[j] * fzij;
  }
  fo[0] = fv; fo[1] = fx; fo[2] = fy; fo[3] = fz;
}

// ---- plain-Ara hand-asm vector kernel -------------------------------------
// ABI: a0=bx a1=by a2=bz a3=bv a4=bq a5=aparams a6=fout a7=N (multiple of VLMAX)
void lavamd_clean(const float *px, const float *py, const float *pz,
                  const float *pv, const float *pq, const float *ap,
                  float *fo, long n);

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void lavamd_clean(const float *px, const float *py, const float *pz,
                  const float *pv, const float *pq, const float *ap,
                  float *fo, long n) {
  __asm__ volatile (
    // ---- load exp constants into pool-scratch f-regs, broadcast to vregs ----
    "la   t6, lavamd_clean_pool\n"
    "flw  ft0, 0(t6)\n"            // exp_hi
    "flw  ft1, 4(t6)\n"            // exp_lo
    "flw  ft2, 8(t6)\n"           // LOG2EF
    "flw  ft3, 12(t6)\n"          // C2
    "flw  ft4, 16(t6)\n"          // p0
    "flw  ft5, 20(t6)\n"          // p1
    "flw  ft6, 24(t6)\n"          // p2
    "flw  ft7, 28(t6)\n"          // p3
    "flw  ft8, 32(t6)\n"          // p4
    "lui  t1, 0x3f318\n"          // C1
    "lui  t2, 0x3f000\n"          // 0.5
    "lui  t3, 0x3f800\n"          // 1.0
    "li   t4, 0x7f\n"             // 127
    "li   t5, 0x17\n"             // 23
    "vsetvli t0, a7, e32, m1, ta, ma\n"
    "vmv.v.i  v9, 0\n"
    "vfmv.v.f v10, ft0\n"
    "vfmv.v.f v12, ft1\n"
    "vfmv.v.f v13, ft2\n"
    "vmv.v.x  v14, t1\n"
    "vfmv.v.f v15, ft3\n"
    "vfmv.v.f v16, ft4\n"
    "vfmv.v.f v17, ft5\n"
    "vfmv.v.f v18, ft6\n"
    "vfmv.v.f v19, ft7\n"
    "vfmv.v.f v20, ft8\n"
    "vmv.v.x  v21, t2\n"
    "vmv.v.x  v22, t3\n"
    "vmv.v.x  v23, t4\n"
    "vmv.v.x  v24, t5\n"
    // ---- particle-A scalars + zero force accumulators ----
    "flw  fa0, 0(a5)\n"           // av
    "flw  fa1, 4(a5)\n"           // ax
    "flw  fa2, 8(a5)\n"           // ay
    "flw  fa3, 12(a5)\n"          // az
    "flw  fa4, 16(a5)\n"          // a2
    "vmv.v.i v1, 0\n"             // fv acc
    "vmv.v.i v2, 0\n"             // fx acc
    "vmv.v.i v3, 0\n"             // fy acc
    "vmv.v.i v4, 0\n"             // fz acc
  "1:\n"
    "vsetvli t0, a7, e32, m1, ta, ma\n"
    "vle32.v v5, (a0)\n"          // bx
    "vle32.v v6, (a1)\n"          // by
    "vle32.v v7, (a2)\n"          // bz
    "vle32.v v8, (a3)\n"          // bv
    // dot = ax*bx + ay*by + az*bz
    "vfmul.vf v25, v5, fa1\n"
    "vfmacc.vf v25, fa2, v6\n"
    "vfmacc.vf v25, fa3, v7\n"
    // r2 = (av + bv) - dot ; u2 = a2*r2 ; arg = -u2
    "vfadd.vf v8, v8, fa0\n"
    "vfsub.vv v25, v8, v25\n"
    "vfmul.vf v25, v25, fa4\n"
    "vfsgnjn.vv v25, v25, v25\n"  // arg = -u2  -> exp input
    // ---- exp(arg) : Cephes f32, v25 in-place -> vij ----
    "vfmin.vv v25, v25, v10\n"
    "vfmax.vv v25, v25, v12\n"
    "vmv1r.v  v26, v16\n"
    "vmv1r.v  v27, v25\n"
    "vfmadd.vv v27, v13, v21\n"
    "vfcvt.x.f.v v28, v27\n"
    "vfcvt.f.x.v v28, v28\n"
    "vmflt.vv v0, v27, v28\n"
    "vmerge.vvm v27, v9, v22, v0\n"
    "vfsub.vv v27, v28, v27\n"
    "vfmul.vv v28, v27, v14\n"
    "vfsub.vv v25, v25, v28\n"
    "vfmul.vv v28, v27, v15\n"
    "vfcvt.x.f.v v27, v27\n"
    "vadd.vv  v27, v27, v23\n"
    "vfsub.vv v25, v25, v28\n"
    "vsll.vv  v27, v27, v24\n"
    "vfmul.vv v28, v25, v25\n"
    "vfmadd.vv v26, v25, v17\n"
    "vfmadd.vv v26, v25, v18\n"
    "vfmadd.vv v26, v25, v19\n"
    "vfmadd.vv v26, v25, v20\n"
    "vfmadd.vv v26, v25, v21\n"
    "vfmadd.vv v26, v28, v25\n"
    "vfadd.vv v25, v26, v22\n"
    "vfmul.vv v25, v25, v27\n"    // v25 = vij
    // ---- forces ----
    "vle32.v v8, (a4)\n"          // bq
    "vfadd.vv v26, v25, v25\n"    // fs = 2*vij
    "vfrsub.vf v5, v5, fa1\n"     // dx = ax - bx
    "vfrsub.vf v6, v6, fa2\n"     // dy = ay - by
    "vfrsub.vf v7, v7, fa3\n"     // dz = az - bz
    "vfmul.vv v5, v26, v5\n"      // fxij
    "vfmul.vv v6, v26, v6\n"      // fyij
    "vfmul.vv v7, v26, v7\n"      // fzij
    "vfmacc.vv v1, v8, v25\n"     // fv += bq*vij
    "vfmacc.vv v2, v8, v5\n"      // fx += bq*fxij
    "vfmacc.vv v3, v8, v6\n"      // fy += bq*fyij
    "vfmacc.vv v4, v8, v7\n"      // fz += bq*fzij
    // advance (t1..t5 free after broadcast)
    "slli t1, t0, 2\n"
    "add  a0, a0, t1\n"
    "add  a1, a1, t1\n"
    "add  a2, a2, t1\n"
    "add  a3, a3, t1\n"
    "add  a4, a4, t1\n"
    "sub  a7, a7, t0\n"
    "bnez a7, 1b\n"
    // ---- reduce accumulators over VLMAX, store 4 forces ----
    "vsetvli t0, zero, e32, m1, ta, ma\n"
    "vmv.v.i v9, 0\n"
    "vfredusum.vs v1, v1, v9\n"
    "vfredusum.vs v2, v2, v9\n"
    "vfredusum.vs v3, v3, v9\n"
    "vfredusum.vs v4, v4, v9\n"
    "vfmv.f.s fa0, v1\n"
    "vfmv.f.s fa1, v2\n"
    "vfmv.f.s fa2, v3\n"
    "vfmv.f.s fa3, v4\n"
    "fsw fa0, 0(a6)\n"
    "fsw fa1, 4(a6)\n"
    "fsw fa2, 8(a6)\n"
    "fsw fa3, 12(a6)\n"
    "ret\n"
    ".balign 4\n"
    "lavamd_clean_pool:\n"
    ".float  88.3762626647949\n"
    ".float -88.3762626647949\n"
    ".float  1.44269504088896341\n"
    ".float -2.12194440e-4\n"
    ".float  1.9875691500e-4\n"
    ".float  1.3981999507e-3\n"
    ".float  8.3334519073e-3\n"
    ".float  4.1665795894e-2\n"
    ".float  1.6666665459e-1\n"
  );
}

int main() {
  printf("\n=== LavaMD N-body (asm baseline) ===\n");
  printf("Particles: %d\n", NPAR);
  // data prep
  for (int j = 0; j < NPAR; ++j) {
    float t = (float)(j + 1);
    bx[j] = 0.01f * t; by[j] = 0.02f * t; bz[j] = 0.015f * t;
    bv[j] = 0.5f + 0.001f * t; bq[j] = 0.3f + 0.0005f * t;
  }
  aparams[0] = 0.7f; aparams[1] = 0.11f; aparams[2] = 0.22f;
  aparams[3] = 0.33f; aparams[4] = 0.05f;

  lavamd_ref(bx, by, bz, bv, bq, aparams, fout_s, NPAR);

  start_timer();
  lavamd_clean(bx, by, bz, bv, bq, aparams, fout_v, NPAR);
  stop_timer();
  printf("vector lavamd_clean: %d cycles\n", (int)get_timer());

  int error = 0;
#ifdef CHECK
  const char *nm[4] = {"fv", "fx", "fy", "fz"};
  for (int k = 0; k < 4; ++k) {
    if (!similarity_check(fout_s[k], fout_v[k], THRESHOLD)) {
      error = 1;
      printf("Error %s: %f != %f\n", nm[k], fout_v[k], fout_s[k]);
    }
  }
  if (!error)
    printf("Check okay. No errors.\n");
#endif
  return error;
}
