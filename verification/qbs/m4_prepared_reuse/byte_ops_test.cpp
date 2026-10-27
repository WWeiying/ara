#include "rvv-byte-ops.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

alignas(64) static unsigned char source[24832],destination[24832];
static void need(bool ok,const char *why) {
    if(!ok) {std::printf("RVV_BYTE_OPS_FAIL reason=%s\n",why);std::exit(1);}
}
static unsigned fc() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vc() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static void state(unsigned f,unsigned v) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0"::"r"(f),"r"(v):"memory");
}
int main() {
    for(size_t i=0;i<sizeof(source);++i) source[i]=static_cast<unsigned char>(i*17+3);
    const size_t lengths[]={0,1,15,16,17,127,128,129,1023,1024,1025,7008,24576};
    unsigned cases=0,states=0;
    for(size_t n:lengths) for(size_t offset:{size_t(0),size_t(1),size_t(7),size_t(63)}) {
        std::memset(destination,0xa5,sizeof(destination));state(113,5);
        auto *d=destination+64+offset;const auto *s=source+offset;
        ggml_riscv_byte_ops::copy(d,s,n);
        need(fc()==113 && vc()==5,"copy_csr");
        need(ggml_riscv_byte_ops::equal(d,s,n),"equal");
        need(fc()==113 && vc()==5,"equal_csr");
        need(n==0 || std::memcmp(d,s,n)==0,"copy_bytes");
        bool guard=true;
        for(size_t i=0;i<sizeof(destination);++i)
            if(i<64+offset || i>=64+offset+n) guard&=destination[i]==0xa5;
        need(guard,"copy_guard");
        if(n) for(size_t p:{size_t(0),n/2,n-1}) {
            d[p]^=1;need(!ggml_riscv_byte_ops::equal(d,s,n),"missed_mismatch");d[p]^=1;
        }
        ++cases;
    }
    for(unsigned f=0;f<32;++f) for(unsigned v=0;v<8;++v) {
        state(96|f,v);
        ggml_riscv_byte_ops::copy(destination+1,source+7,1025);
        need(ggml_riscv_byte_ops::equal(destination+1,source+7,1025),"state_bytes");
        need(fc()==(96|f) && vc()==v,"state_matrix");++states;
    }
    ggml_riscv_byte_ops::copy(nullptr,nullptr,0);
    need(ggml_riscv_byte_ops::equal(nullptr,nullptr,0),"empty_null");state(0,0);
    std::printf("RVV_BYTE_OPS_PASS cases=%u states=%u\n",cases,states);
    return cases==52 && states==256 ? 0:2;
}
