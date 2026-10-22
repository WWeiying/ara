#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define STRIDED_REPLAY 1
#define NEGATIVE_STRIDE 1
#define ZERO_STRIDE 0
#define INDEXED_REPLAY 0
#define REPLAY_FIELDS 1
#define REPLAY_ELEMENTS 8
#define CAPACITY_LIMIT 128
typedef uint16_t word;
typedef uint16_t index_word;
static word input[128],output[130];
static index_word offsets[128];
static uint8_t mask[16];
static unsigned cap=64,store_case,expected_start;
static uintptr_t mapping,target,expected_address;
static long stride;
static word backing[4096];
static unsigned active(unsigned i){return (mask[i/8]>>(i%8))&1;}
static word original(uintptr_t address){return (word)(((address-mapping)/sizeof(word))*37+11);}
static word poison(unsigned i){return (word)(input[i]^0x5b);}
static uintptr_t element_address(unsigned i){
#if STRIDED_REPLAY
    return target+i*stride;
#else
    return target+(INDEXED_REPLAY ? offsets[i]:i*REPLAY_FIELDS*sizeof(word));
#endif
}
static uintptr_t field_address(unsigned i,unsigned field){return element_address(i)+field*sizeof(word);}
static unsigned logical_element(uintptr_t address){
    for(unsigned i=0;i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
        if(field_address(i,f)==address
#if ZERO_STRIDE
           && active(i)
#endif
          )return i*REPLAY_FIELDS+f;
    return REPLAY_ELEMENTS*REPLAY_FIELDS;
}

int main(int argc,char **argv) {
  if(argc!=7)return 2;
  unsigned unmapped=(unsigned)atoi(argv[1]);
  store_case=(unsigned)atoi(argv[2]);
  unsigned boundary=(unsigned)atoi(argv[3]),mode=(unsigned)atoi(argv[4]);
  unsigned split=(unsigned)atoi(argv[5]),gap=(unsigned)atoi(argv[6]);
  (void)unmapped;
  mapping=(uintptr_t)backing;
        unsigned accessible_fields=split ? REPLAY_FIELDS/2:0;
#if STRIDED_REPLAY
#if ZERO_STRIDE
        stride=0;
        target=mapping+4096-accessible_fields*sizeof(word);
#else
        stride=(REPLAY_FIELDS+gap)*sizeof(word);
#if NEGATIVE_STRIDE
        target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
        stride=-stride;
#else
        target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
#endif
#endif
#else
        target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
#endif
        for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
            input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
        for(unsigned i=0;i<CAPACITY_LIMIT;++i){
#if INDEXED_REPLAY && REPLAY_FIELDS>1
            /* Keep the first protected segment fixed to exercise field splits. */
            unsigned slot=i<boundary ? (i+1)%boundary:i==boundary ? boundary:
                          i<REPLAY_ELEMENTS ? boundary+1+(i-boundary)%(REPLAY_ELEMENTS-boundary-1):i;
            offsets[i]=(index_word)(slot*REPLAY_FIELDS*sizeof(word));
#else
            unsigned slot=i<boundary ? (i+1)%boundary:
                          i<8 ? boundary+(i-boundary+1)%(8-boundary):i;
            offsets[i]=(index_word)(slot*sizeof(word));
#endif
        }
        for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
        for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
        expected_start=REPLAY_ELEMENTS;
        for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
        expected_address=element_address(expected_start);
  unsigned faults=expected_start<REPLAY_ELEMENTS;
  printf("C %u %ld %ld %ld\n",expected_start,(long)(expected_address-mapping),(long)(target-mapping),stride);
  for(unsigned i=0;i<128;++i)printf("I %u %u %u\n",i,input[i],offsets[i]);
  for(unsigned i=0;i<16;++i)printf("K %u %u\n",i,mask[i]);
  for(unsigned i=0;i<130;++i)printf("B %u %u\n",i,output[i]);
        for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
            word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
            printf("V %u %u\n",i,(unsigned)wanted);
        }
        for(unsigned i=0;i<8192/sizeof(word);++i){
            uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
            unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
            if(store_case && j<REPLAY_ELEMENTS){
                if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
            }else if(!store_case && faults && j<expected_start){
                if(active(j))wanted^=0x5b;
            }
            printf("D %u %u %u\n",i,(unsigned)original(at),(unsigned)wanted);
        }

return 0;
}
