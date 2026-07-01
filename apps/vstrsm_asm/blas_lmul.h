// ── Per-BLAS_LMUL parameterization for the prefetch-enabled BLAS kernels ─────
// The m4 "#else" body of vssymv/vsgemv/vstrsm is parameterized through these
// macros so the same source compiles for LMUL = 2, 4, 8 (BLAS_LMUL=1 keeps the
// original fixed-32 m1 .inc as a no-prefetch reference).
//
// Prefetch-enabled structure (so the enable gate avl>=2*vl actually holds):
//   VL = VLMAX  via  AVL = 2*VLMAX (= LMUL*64);  matrix width = VLMAX (= LMUL*32);
//   row stride  = VLMAX*4 (= LMUL*128);  loop count M = rows (a3, runtime).
//   Row-major rows are contiguous -> ONE unit-stride prefetch stream.
//   The data buffer (32768 floats) is read at width VLMAX, so M*VLMAX<=32768
//   (m8 -> M<=128).  Values are irrelevant (the TB checks task_done, not output).
//
// vreg groups are LMUL-aligned: group g uses vreg number g*BLAS_LMUL
//   BL_G1=1*LMUL, BL_G2=2*LMUL, BL_G3=3*LMUL  (group 0 = v0, implicit)
//   m2 -> v2,v4,v6 ; m4 -> v4,v8,v12 ; m8 -> v8,v16,v24
//
// prefetch lead BL_PFM = 1X (mul=0) for EVERY LMUL and stream count.  Each
// iteration consumes exactly one descriptor (one VLMAX-wide row), so 1X prefetches
// addr+num_bytes*1 = the NEXT row = next iteration's data — exactly the goal.  A
// larger lead overshoots (prefetches i+2/i+4): more warm-up misses, more
// over-prefetch past the array end (the stale-FIFO clog fixed for vsgemm), more
// buffer use, and NO better steady-state hit rate.  See docs/prefetch_config.md.
#ifndef BLAS_LMUL_H
#define BLAS_LMUL_H

#define BL__STR(x) #x
#define BL_STR(x)  BL__STR(x)

#if   BLAS_LMUL == 2
  #define BL_G1 2
  #define BL_G2 4
  #define BL_G3 6
#elif BLAS_LMUL == 4
  #define BL_G1 4
  #define BL_G2 8
  #define BL_G3 12
#elif BLAS_LMUL == 8
  #define BL_G1 8
  #define BL_G2 16
  #define BL_G3 24
#else
  #error "blas_lmul.h: BLAS_LMUL must be 2, 4, or 8 (1 = original m1 .inc)"
#endif

// prefetch lead = 1X (next iteration) for all LMUL / stream counts.
#define BL_PFM 1

#endif
