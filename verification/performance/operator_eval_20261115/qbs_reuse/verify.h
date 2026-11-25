#ifndef QBS_REUSE_VERIFY_H
#define QBS_REUSE_VERIFY_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef struct { unsigned checked, errors, first_bad; } reuse_check_t;

static inline reuse_check_t reuse_check_init(void) {
  return (reuse_check_t){0,0,~0u};
}

__attribute__((noinline,noclone))
static reuse_check_t reuse_check_bytes(const void *actual, const void *expected, unsigned bytes) {
  const volatile unsigned char *a=actual, *e=expected;
  reuse_check_t r=reuse_check_init();
  for (unsigned i=0;i<bytes;++i) {
    unsigned bad=a[i]!=e[i];
    if (bad && !r.errors) r.first_bad=i;
    r.errors+=bad; ++r.checked;
  }
  return r;
}

__attribute__((noinline,noclone))
static reuse_check_t reuse_check_guard(const void *actual, unsigned bytes) {
  const volatile unsigned char *a=actual;
  reuse_check_t r=reuse_check_init();
  for (unsigned i=0;i<bytes;++i) {
    unsigned bad=a[i]!=0xa5;
    if (bad && !r.errors) r.first_bad=i;
    r.errors+=bad; ++r.checked;
  }
  return r;
}

__attribute__((noinline,noclone))
static reuse_check_t reuse_check_output(const float *actual, const float *expected,
                                       unsigned m, unsigned n, int group_major, int exact) {
  const volatile float *a=actual, *e=expected;
  reuse_check_t r=reuse_check_init();
  for (unsigned row=0;row<m;++row) for (unsigned col=0;col<n;++col) {
    const unsigned i=row*n+col, j=group_major ? (col/32*m+row)*32+col%32 : i;
    float af=a[j], ef=e[i];
    uint32_t ab,eb; memcpy(&ab,&af,4); memcpy(&eb,&ef,4);
    unsigned bad;
    if (exact) bad=ab!=eb;
    else {
      double av=af, ev=ef, diff=av-ev;
      if (diff<0) diff=-diff;
      if (ev<0) ev=-ev;
      bad=(ab&0x7f800000u)==0x7f800000u || (eb&0x7f800000u)==0x7f800000u ||
          diff>0.0002+0.0002*ev;
    }
    if (bad && !r.errors) r.first_bad=i;
    r.errors+=bad; ++r.checked;
  }
  return r;
}
#endif
