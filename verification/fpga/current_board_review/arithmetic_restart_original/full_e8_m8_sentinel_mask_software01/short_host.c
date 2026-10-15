#define _GNU_SOURCE
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "../full_e8_m8_block_unrolled01/dictionary.h"
#define raw_word old_raw_word
#define initialize_output old_initialize_output
#define initialize_mask old_initialize_mask
#define packed_mismatch old_packed_mismatch
#include "../full_e8_m8_block_unrolled01/packed.h"
#undef raw_word
#undef initialize_output
#undef initialize_mask
#undef packed_mismatch
#include "packed.h"
static void require(int ok,const char *why){if(!ok){fprintf(stderr,"%s\n",why);exit(1);}}
static void fill(uint8_t *p,unsigned ordinal){
    for(unsigned b=0;b<16;++b)memcpy(p+64*b,expected_dictionary+8*(unsigned)expected_indices[ordinal][b],64);
    uint16_t tail=(uint16_t)expected_dictionary[8*(unsigned)expected_indices[ordinal][16]];
    memcpy(p+1024,&tail,2);
}
int main(void){
    const unsigned selected[]={0,1365,2730,4094,9,45,1257,1278,1299};
    uint8_t oldmask[128],newmask[128];unsigned positives=0,negatives=0;
    for(unsigned mode=0;mode<3;++mode){
        memset(oldmask,0x71,128);memset(newmask,0x71,128);
        old_initialize_mask(oldmask,mode);initialize_mask(newmask,mode);
        require(memcmp(oldmask,newmask,128)==0,"128B mask equality");
        require(memcmp(newmask,physical_masks[mode],128)==0,"actual immutable mask table");
        for(unsigned bit=0;bit<1024;++bit){
            unsigned want=mode==0 || (mode==1 ? (bit&1) : bit%7==2);
            require(((newmask[bit/8]>>(bit%8))&1)==want,"original selected policy across all1024 predicate bits");
        }
    }
    unsigned mask_negatives=0;
    for(unsigned mode=0;mode<3;++mode){
        initialize_mask(newmask,mode);
        for(unsigned byte=0;byte<128;++byte){
            newmask[byte]^=0x80;
            require(memcmp(newmask,physical_masks[mode],128)!=0,"each mask byte including high64 must matter");
            newmask[byte]^=0x80;++mask_negatives;
        }
        for(unsigned wrong=0;wrong<3;++wrong)if(wrong!=mode){
            initialize_mask(newmask,wrong);
            require(memcmp(newmask,physical_masks[mode],128)!=0,"wrong mode rejected over full128B");
            ++mask_negatives;
        }
    }
    uint8_t oldinit[1026],newinit[1026];
    old_initialize_output(oldinit);initialize_output(newinit);
    require(memcmp(oldinit,newinit,1026)==0,"typed initializer untouched");
    long page=sysconf(_SC_PAGESIZE);require(page>=2048,"page bound");
    uint8_t *mem=mmap(NULL,(size_t)page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    require(mem!=MAP_FAILED,"mmap");
    require(mprotect(mem+page,(size_t)page,PROT_NONE)==0,"tail guard page");
    uint8_t *p=mem+page-1026;
    for(unsigned j=0;j<sizeof(selected)/sizeof(selected[0]);++j){
        unsigned ordinal=selected[j];fill(p,ordinal);
        require(old_packed_mismatch(p,ordinal)==0 && packed_mismatch(p,ordinal)==0,"positive real ordinal/full protected tail");
        ++positives;
        for(unsigned byte=0;byte<1026;++byte){
            p[byte]^=0x80;
            require(old_packed_mismatch(p,ordinal)==1 && packed_mismatch(p,ordinal)==1,"each-byte/high-bit/guard/tail negative");
            p[byte]^=0x80;++negatives;
        }
        require(packed_mismatch(p,ordinal)==0,"no stale mismatch/cache after mutation");
    }
    require(munmap(mem,(size_t)page*2)==0,"munmap");
    printf("SHORT_C_ONLY positives=%u byte_negatives=%u mask_modes=3 mask_negatives=%u bytes=1026 full4095_streams=0\n",positives,negatives,mask_negatives);
    return 0;
}
