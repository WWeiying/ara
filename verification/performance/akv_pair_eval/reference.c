/* Host-only tile64 oracle. Keep the F16 PV recurrence, not F32 accumulation. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static float fp16(float x) { return (float)(_Float16)x; }
static float vector_exp(float x) {
  if (x < -0x1.5d58ap+6f) return 0;
  float z = fmaf(0x1.715476p+0f, x, 0x1.8p23f);
  float n = z - 0x1.8p23f;
  float b = fmaf(-0x1.62e4p-1f, n, x);
  b = fmaf(-0x1.7f7d1cp-20f, n, b);
  uint32_t bits;
  memcpy(&bits, &z, 4);
  bits = (bits << 23) + UINT32_C(0x3f800000);
  float k;
  memcpy(&k, &bits, 4);
  float u = b * b;
  float j = fmaf(fmaf(0x1.0e4020p-7f, b, 0x1.573e2ep-5f), u,
                 fmaf(0x1.555e66p-3f, b, 0x1.fffdb6p-2f));
  j = fmaf(j, u, b * 0x1.ffffecp-1f);
  return fmaf(j, k, k);
}

static void read_file(const char *dir, const char *name, void *data, size_t size) {
  char path[4096];
  if (snprintf(path, sizeof(path), "%s/%s", dir, name) >= (int)sizeof(path)) exit(2);
  FILE *f = fopen(path, "rb");
  if (!f || fread(data, 1, size, f) != size || fgetc(f) != EOF) exit(2);
  fclose(f);
}

int main(int argc, char **argv) {
  if (argc != 3) return 2;
  _Float16 q[2][128], k[256][128], v[256][128], mask[256];
  read_file(argv[1], "decode_query_f16.bin", q, sizeof(q));
  read_file(argv[1], "decode_key.bin", k, sizeof(k));
  read_file(argv[1], "decode_value.bin", v, sizeof(v));
  read_file(argv[1], "decode_mask.bin", mask, sizeof(mask));
  float out[2][128];
  for (unsigned h = 0; h < 2; ++h) {
    float acc[128] = {0}, maximum = -INFINITY, sum = 0;
    for (unsigned start = 0; start < 137; start += 64) {
      unsigned count = 137 - start < 64 ? 137 - start : 64;
      float scores[64], tile_max = -INFINITY;
      for (unsigned t = 0; t < count; ++t) {
        float dot = 0;
        for (unsigned d = 0; d < 128; ++d) dot = fmaf(q[h][d], k[start+t][d], dot);
        scores[t] = dot * 0x1.6a09e6p-4f + (float)mask[start+t];
        if (scores[t] > tile_max) tile_max = scores[t];
      }
      float next = tile_max > maximum ? tile_max : maximum;
      float old_scale = maximum == -INFINITY ? 0 : expf(maximum - next);
      double weights_sum = 0;
      for (unsigned t = 0; t < count; ++t) {
        scores[t] = vector_exp(scores[t] - next);
        weights_sum += scores[t];
      }
      float scaled_sum = sum * old_scale;
      sum = (float)((double)scaled_sum + weights_sum);
      maximum = next;
      for (unsigned d = 0; d < 128; ++d) {
        acc[d] = fp16(acc[d] * fp16(old_scale));
        for (unsigned t = 0; t < count; ++t)
          acc[d] = (float)(_Float16)fma((double)fp16(scores[t]), (double)v[start+t][d], (double)acc[d]);
      }
    }
    float inverse = 1.0f / sum;
    for (unsigned d = 0; d < 128; ++d) out[h][d] = acc[d] * inverse;
  }
  FILE *f = fopen(argv[2], "wb");
  if (!f || fwrite(out, 1, sizeof(out), f) != sizeof(out)) return 2;
  return fclose(f) != 0;
}
