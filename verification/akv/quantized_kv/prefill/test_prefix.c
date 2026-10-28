#include "prefix_schedule.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>

typedef struct {
  unsigned rows, dim, base, visible[8], qk, values, elements, fail_qk, fail_value;
} fixture;

static float score(unsigned row, unsigned token) {
  return ((int)((row * 7 + token * 13) % 29) - 14) * 0.03125f;
}
static float element(unsigned token, unsigned d) {
  return ((int)((token * 17 + d * 5) % 31) - 15) * 0.0625f;
}
static int qk(void *opaque, unsigned row, unsigned rows, unsigned first,
              unsigned n, float *out, size_t stride) {
  fixture *f = opaque;
  if (++f->qk == f->fail_qk) return 1;
  assert(rows == 1 || rows == 2 || rows == 4);
  assert(row + rows <= f->rows && n && n <= 32);
  for (unsigned r = 0; r < rows; ++r) {
    assert(first + n <= f->visible[row + r]);
    for (unsigned t = 0; t < n; ++t) {
      out[r * stride + t] = score(f->base + row + r, first + t);
      ++f->elements;
    }
  }
  return 0;
}
static int value(void *opaque, unsigned token, float *out, unsigned dim) {
  fixture *f = opaque;
  if (++f->values == f->fail_value) return 1;
  unsigned maximum = 0;
  for (unsigned r = 0; r < f->rows; ++r)
    if (f->visible[r] > maximum) maximum = f->visible[r];
  assert(token < maximum && dim == f->dim);
  for (unsigned d = 0; d < dim; ++d) out[d] = element(token, d);
  return 0;
}
static void scale(int n, float *out, float s) {
  for (int i = 0; i < n; ++i) out[i] *= s;
}
static void mad(int n, float *out, const float *v, float s) {
  for (int i = 0; i < n; ++i) out[i] = fmaf(v[i], s, out[i]);
}

int main(void) {
  const unsigned dims[] = {32, 64, 96, 128, 256};
  const unsigned limits[] = {1, 31, 32, 33, 63, 64, 65, 128};
  unsigned cases = 0;
  for (unsigned rows = 1; rows <= 8; ++rows)
    for (unsigned di = 0; di < 5; ++di)
      for (unsigned ti = 0; ti < 8; ++ti)
        for (unsigned pattern = 0; pattern < 3; ++pattern) {
          fixture f = {.rows=rows, .dim=dims[di]};
          unsigned maximum = 0, total = 0;
          for (unsigned r = 0; r < rows; ++r) {
            f.visible[r] = pattern == 0 ? limits[ti] : 1 +
                ((pattern == 1 ? r : rows - 1 - r) * 17 + limits[ti] - 1) % limits[ti];
            if (f.visible[r] > maximum) maximum = f.visible[r];
            total += f.visible[r];
          }
          float ref[8 * 264], got[8 * 264];
          memset(ref, 0xa5, sizeof(ref)); memset(got, 0xa5, sizeof(got));
          akv_quant_online_workspace_t w;
          feclearexcept(FE_ALL_EXCEPT);
          for (unsigned r = 0; r < rows; ++r) {
            fixture one = {.rows=1, .dim=f.dim, .base=r, .visible={f.visible[r]}};
            akv_quant_online_plan_t p = {1, f.dim, f.visible[r], 0.5f, &one, qk, value, scale, mad};
            assert(akv_quant_online_head_major(&p, ref + r * 264, 264, &w) == 0);
          }
          const int flags = fetestexcept(FE_ALL_EXCEPT);
          feclearexcept(FE_ALL_EXCEPT);
          akv_quant_online_plan_t p = {rows, f.dim, limits[ti], 0.5f, &f, qk, value, scale, mad};
          assert(quant_prefill_prefix_schedule(&p, f.visible, got, 264, &w) == 0);
          assert(memcmp(ref, got, sizeof(ref)) == 0 && flags == fetestexcept(FE_ALL_EXCEPT));
          assert(f.elements == total && f.values == maximum);
          for (unsigned r = 0; r < rows; ++r)
            for (unsigned d = 0; d < f.dim; ++d) {
              double sum = 0, numerator = 0;
              for (unsigned t = 0; t < f.visible[r]; ++t) {
                double weight = exp((double)score(r, t) * 0.5);
                sum += weight; numerator += weight * element(t, d);
              }
              assert(fabs(got[r * 264 + d] - numerator / sum) < 1e-5);
            }
          ++cases;
        }
  fixture f = {.rows=2, .dim=32, .visible={1,0}};
  float output[64], saved[64]; memset(output, 0xa5, sizeof(output)); memcpy(saved, output, sizeof(output));
  akv_quant_online_workspace_t w;
  akv_quant_online_plan_t p = {2, 32, 33, 0.5f, &f, qk, value, scale, mad};
  assert(quant_prefill_prefix_schedule(&p, f.visible, output, 32, &w) == AKV_QUANT_BAD_ARGUMENT);
  assert(!memcmp(output, saved, sizeof(output)) && !f.qk && !f.values);
  f.visible[1] = 33; f.fail_qk = 1;
  assert(quant_prefill_prefix_schedule(&p, f.visible, output, 32, &w) == AKV_QUANT_QK_FAILED);
  assert(f.qk == 1 && f.values == 0);
  f.qk = 0; f.fail_qk = 0; f.fail_value = 1;
  assert(quant_prefill_prefix_schedule(&p, f.visible, output, 32, &w) == AKV_QUANT_VALUE_FAILED);
  assert(f.values == 1);
  printf("PREFIX_HOST_PASS cases=%u bitexact=1 flags=1 masked_qk=0 oracle=1 failure_paths=1\n", cases);
}
