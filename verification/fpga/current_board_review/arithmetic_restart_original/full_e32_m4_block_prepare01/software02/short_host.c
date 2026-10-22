#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const unsigned char *base;
static unsigned reads;
static void actual_event(const unsigned char *p) {
    if (reads >= 65 || p != base + 8 * reads) abort();
    ++reads;
}
#include "short_packed.h"
int main(void) {
    static uint64_t blocks[2252][8];
    const uint16_t ids[9] = {0,0,1,1,0,1,1,0,1};
    unsigned char bytes[522];
    unsigned char *out = bytes + 1;
    for (unsigned i=0;i<16;++i) blocks[i/8][i%8]=UINT64_C(0xdeadbeef12340000)+i;
    for (unsigned trial=0;trial<6;++trial) {
        memset(bytes,0xa5,sizeof(bytes));
        for (unsigned i=0;i<65;++i) memcpy(out+8*i,&blocks[ids[i/8]][i%8],8);
        if (trial==1 || trial==4) out[0]^=1;
        if (trial==2 || trial==5) out[260]^=0x80;
        if (trial==3 || trial==4 || trial==5) out[519]^=1;
        base=out;reads=0;
        unsigned bad=e32m4_packed_mismatch(out,ids,blocks);
        if (bad!=(trial!=0) || reads!=65 || bytes[0]!=0xa5 || bytes[521]!=0xa5) abort();
        printf("SHORT trial=%u mismatch=%u actual_reads=%u\n",trial,bad,reads);
    }
    return 0;
}
