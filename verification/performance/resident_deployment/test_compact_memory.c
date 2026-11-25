#include <stddef.h>
void *memcpy(void *to, const void *from, size_t size) {
  unsigned char *d=to; const unsigned char *s=from;
  for(size_t i=0;i<size;++i) d[i]=s[i];
  return to;
}
