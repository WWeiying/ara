#include "qbs/qbs_abi.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

extern "C" bool m4_produce(const float *,void *,int64_t);
extern "C" bool m4_tiled_produce(const float *,void *,int64_t);
extern "C" const float real_input[];
alignas(64) static unsigned char baseline[7008+128],candidate[7008+128];
alignas(64) static float generated[4*256],saved[4*256];
static unsigned checks=0;
static void need(bool ok,const char *why) {
    if(!ok) {std::printf("TILED_M4_FAIL check=%u reason=%s\n",checks,why);std::exit(1);}
}
static void state(unsigned flags,unsigned vector_state) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0"::"r"(flags),"r"(vector_state):"memory");
}
static unsigned fc() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vc() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static void compare(const float *input,int64_t k,unsigned flags,unsigned vector_state) {
    std::memset(baseline,0xa5,sizeof(baseline));std::memset(candidate,0xa5,sizeof(candidate));
    state(flags,vector_state);const bool first=m4_produce(input,baseline+64,k);
    const unsigned expected_fc=fc(),expected_vc=vc();
    state(flags,vector_state);const bool second=m4_tiled_produce(input,candidate+64,k);
    need(fc()==expected_fc && vc()==expected_vc,"architectural_state");
    need(first==second,"fallback_selection");
    need(std::memcmp(baseline,candidate,sizeof(baseline))==0,"prepared_bytes_or_guards");
    const size_t bytes=size_t(k/256)*4*QBS_Q8_K_BLOCK_BYTES;
    for(size_t i=0;i<64;++i) need(candidate[i]==0xa5 && candidate[64+bytes+i]==0xa5,"canary");
    ++checks;
}
int main() {
    for(unsigned group=0;group<3;++group)
        for(unsigned flags=0;flags<32;++flags)
            for(unsigned vector_state=0;vector_state<8;++vector_state)
                compare(real_input+group*4*1536,1536,flags,vector_state);
    for(unsigned kind=0;kind<4;++kind) {
        for(unsigned i=0;i<4*256;++i) {
            if(kind==0) generated[i]=0.0f;
            else if(kind==1) generated[i]=(i&1) ? -1.0f:1.0f;
            else if(kind==2) {const uint32_t word=(i&1)<<31;std::memcpy(generated+i,&word,4);}
            else generated[i]=float(int((i*17)%127)-63)/512.0f;
        }
        std::memcpy(saved,generated,sizeof(saved));
        for(unsigned frm=0;frm<=4;++frm)
            for(unsigned sticky:{0u,17u}) compare(generated,256,(frm<<5)|sticky,5);
        need(std::memcmp(saved,generated,sizeof(saved))==0,"input_modified");
    }
    need(checks==808,"test_extent");
    std::printf("TILED_M4_PASS checks=%u real_groups=3 generated_cases=4 bytes=7008\n",checks);
}
