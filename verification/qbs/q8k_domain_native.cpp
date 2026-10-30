#include "q8k_m4_domain_vla.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <sys/reboot.h>
#include <unistd.h>

static size_t datasets=0,checks=0;
static uint64_t digest=UINT64_C(14695981039346656037);
[[noreturn]] static void finish(int code) {
    std::printf("Q8K_DOMAIN_EXIT=%d\n",code);std::fflush(nullptr);sync();reboot(RB_POWER_OFF);
    for (;;) pause();
}
[[noreturn]] static void fail(const char * reason) {
    std::printf("Q8K_DOMAIN_FAIL case=%zu check=%zu reason=%s\n",datasets,checks,reason);finish(1);
}
static bool reference(const float * x,int64_t k) {
    for (int64_t b=0;b<k/256;++b) for (int r=0;r<4;++r) {
        uint32_t maximum=0;
        for (int j=0;j<256;++j) {
            uint32_t bits;std::memcpy(&bits,x+r*k+b*256+j,4);bits &= 0x7fffffffU;
            if (bits>=0x7f800000U || (bits && bits<0x00800000U))return false;
            if(bits>maximum)maximum=bits;
        }
        if(maximum && (maximum<0x08800000U || maximum>0x77000000U))return false;
    }
    return true;
}
static bool candidate(const float * x,int64_t k,int cap) {
    using qbs_q8k_m4_domain_vla::check;
    switch(cap) {
        case 1:return check<1>(x,k);case 7:return check<7>(x,k);
        case 16:return check<16>(x,k);case 32:return check<32>(x,k);
        case 64:return check<64>(x,k);case 256:return check<256>(x,k);
        default:fail("cap");
    }
}
static float value(uint32_t bits) {float x;std::memcpy(&x,&bits,4);return x;}
static void test(std::vector<float> & x) {
    const auto unchanged=x;
    const int64_t k=x.size()/4;
    const bool expected=reference(x.data(),k);
    const unsigned sticky[]={0,1,31},vcsrs[]={0,5,7};
    for (unsigned frm=0;frm<5;++frm) for (unsigned env=0;env<3;++env)
        for (int cap:{1,7,16,32,64,256}) {
            const unsigned initial=frm*32+sticky[env],v=vcsrs[env];
            asm volatile("fscsr %0; csrw vcsr,%1" : : "r"(initial),"r"(v) : "memory");
            const bool actual=candidate(x.data(),k,cap);
            unsigned fcsr,vcsr;
            asm volatile("frcsr %0; csrr %1,vcsr" : "=r"(fcsr),"=r"(vcsr) : : "memory");
            if(actual!=expected)fail("classification");
            if(fcsr!=initial || vcsr!=v)fail("csr");
            digest=(digest^unsigned(actual))*UINT64_C(1099511628211);++checks;
        }
    if(std::memcmp(x.data(),unchanged.data(),x.size()*4))fail("input_modified");
    ++datasets;
}
int main() {
    const uint32_t boundaries[]={0,0x80000000U,1,0x80000001U,0x007fffffU,0x807fffffU,
        0x00800000U,0x80800000U,0x087fffffU,0x08800000U,0x08800001U,0x76ffffffU,
        0x77000000U,0x77000001U,0x7f7fffffU,0xff7fffffU,0x7f800000U,0xff800000U,
        0x7fc00000U,0xffc12345U,0x7f800001U,0x3f800000U,0xbf800000U,0x00008000U};
    size_t vlenb;asm volatile("csrr %0,vlenb":"=r"(vlenb));
    std::printf("Q8K_DOMAIN_BEGIN vlen=%zu\n",vlenb*8);std::fflush(stdout);
    std::vector<float> x;
    for(uint32_t bits:boundaries){x.assign(1024,value(bits));test(x);}
    for(uint32_t bits:boundaries)for(size_t position:{size_t(0),size_t(7),size_t(255),size_t(2047)}){
        x.assign(2048,1.0f);x[position]=value(bits);test(x);
    }
    uint32_t random=0x289421abU;
    for(int trial=0;trial<8;++trial){
        x.resize(1024*(1+trial%3));
        for(float & f:x){random=1664525U*random+1013904223U;f=value((random&0x807fffffU)|((30+(random>>23)%200)<<23));}
        test(x);
    }
    const char * names[]={"real_attn_first","real_attn_last","real_gate_first","real_gate_last","real_down_first","real_down_last"};
    for(unsigned i=0;i<6;++i){
        char path[80];std::snprintf(path,sizeof(path),"/%s.bin",names[i]);
        FILE * f=std::fopen(path,"rb");x.resize(4*(i<4?1536:8960));
        if(!f || std::fread(x.data(),4,x.size(),f)!=x.size() || std::fgetc(f)!=EOF || std::ferror(f))fail("capture");
        std::fclose(f);test(x);
    }
    if(datasets!=134 || checks!=12060)fail("counts");
    std::printf("Q8K_DOMAIN_PASS datasets=%zu checks=%zu digest=%016llx csr=unchanged input=unchanged\n",datasets,checks,(unsigned long long)digest);
    finish(0);
}
