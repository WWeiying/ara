#include "printf.h"
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>

extern "C" void original_rms_norm(const float *,const float *,unsigned,unsigned,float,float *);
extern "C" void candidate_rms_norm(const float *,const float *,unsigned,unsigned,float,float *);
extern "C" void strict_original_rms_norm(const float *,const float *,unsigned,unsigned,float,float *);
extern "C" void strict_candidate_rms_norm(const float *,const float *,unsigned,unsigned,float,float *);
extern "C" double strict_original_rms_sum(const float *,unsigned);
extern "C" double strict_candidate_rms_sum(const float *,unsigned);
extern "C" const float rms_input[],rms_weight[],rms_expected[],rms_epsilon[];
extern "C" const float rms_decode_input[],rms_decode_expected[];
alignas(64) static float output[2][8192+32];
alignas(64) static float boundary[2048];
extern "C" [[noreturn]] void ggml_abort(const char *,int,const char *,...) {
    printf("RMS_NORM_FAIL reason=upstream_assert\n");std::exit(1);
}
static uint64_t cycle() {uint64_t x;asm volatile("fence rw,rw;rdcycle %0":"=r"(x)::"memory");return x;}
static unsigned fcsr() {unsigned x;asm volatile("frcsr %0":"=r"(x)::"memory");return x;}
static unsigned vcsr() {unsigned x;asm volatile("csrr %0,vcsr":"=r"(x)::"memory");return x;}
static unsigned vstart() {unsigned x;asm volatile("csrr %0,vstart":"=r"(x)::"memory");return x;}
static unsigned checksum(const void *data,size_t size) {
    auto p=static_cast<const unsigned char *>(data);unsigned h=2166136261u;
    for(size_t i=0;i<size;++i)h=(h^p[i])*16777619u;
    return h;
}
int main() {
    const unsigned order[]={0,1,1,0};unsigned errors=0;
    printf("RMS_NORM_SCOPE source=ggml_fused_rms_norm width=2048 decode_rows=1 prefill_rows=4 order=ABBA timing=complete_call\n");
    const unsigned cases[]={1u,4u};
    for(unsigned rows:cases) {
        const float *input=rows==1?rms_decode_input:rms_input;
        const float *expected=rows==1?rms_decode_expected:rms_expected;
        unsigned reference_flags=0,reference_hash=0;
        for(unsigned trial=0;trial<4;++trial) {
            const unsigned candidate=order[trial];float *dst=output[candidate]+16;
            std::memset(output[candidate],0xa5,sizeof(output[candidate]));
            asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0":::"memory");
            const auto execute=candidate?candidate_rms_norm:original_rms_norm;
            const uint64_t begin=cycle();execute(input,rms_weight,2048,rows,rms_epsilon[0],dst);
            const uint64_t elapsed=cycle()-begin;
            const unsigned fc=fcsr(),vc=vcsr(),vs=vstart();
            unsigned local=std::memcmp(dst,expected,rows*2048*4)!=0;
            const auto *raw=reinterpret_cast<const unsigned char *>(output[candidate]);
            for(unsigned i=0;i<64;++i)local+=raw[i]!=0xa5;
            for(size_t i=64+rows*2048*4;i<sizeof(output[candidate]);++i)local+=raw[i]!=0xa5;
            for(unsigned i=0;i<rows*2048;++i)local+=!std::isfinite(dst[i]);
            const unsigned hash=checksum(dst,rows*2048*4);
            if(!trial){reference_flags=fc;reference_hash=hash;}
            local+=fc!=reference_flags || hash!=reference_hash || vc!=5 || vs!=0;
            errors+=local;
            printf("RMS_NORM_TRIAL rows=%u trial=%u candidate=%u cycles=%lu fcsr=%u vcsr=%u vstart=%u checksum=%u errors=%u\n",
                   rows,trial,candidate,(unsigned long)elapsed,fc,vc,vs,hash,local);
        }
    }
    unsigned checks=0;
    const unsigned widths[]={1,31,32,33,127,128,129,257,1024};
    for(unsigned rm=0;rm<5;++rm)for(unsigned width:widths) {
        unsigned fc[2];
        for(unsigned mode=0;mode<2;++mode) {
            const unsigned initial=rm<<5;
            asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0"::"r"(initial):"memory");
            (mode?strict_candidate_rms_norm:strict_original_rms_norm)(rms_input,rms_weight,width,1,rms_epsilon[0],output[mode]);
            fc[mode]=fcsr();errors+=vcsr()!=5 || vstart()!=0;
        }
        errors+=fc[0]!=fc[1] || std::memcmp(output[0],output[1],width*4)!=0;++checks;
    }
    const uint32_t specials[]={0,0x80000000u,1,0x7f7fffffu,0x7f800000u,0xff800000u,0x7fc12345u,0x7f812345u};
    for(uint32_t bits:specials) {
        std::memcpy(boundary,rms_input,2048*4);std::memcpy(boundary,&bits,4);unsigned fc[2];
        for(unsigned mode=0;mode<2;++mode) {
            asm volatile("csrwi fcsr,0;csrwi vcsr,5;csrwi vstart,0":::"memory");
            (mode?strict_candidate_rms_norm:strict_original_rms_norm)(boundary,rms_weight,3,1,rms_epsilon[0],output[mode]);
            fc[mode]=fcsr();errors+=vcsr()!=5 || vstart()!=0;
        }
        errors+=fc[0]!=fc[1] || std::memcmp(output[0],output[1],3*4)!=0;++checks;
    }
    unsigned sum_checks=0;
    for(unsigned rm=0;rm<5;++rm)for(unsigned family=0;family<2;++family) {
        const unsigned width=family?257:129;
        for(unsigned i=0;i<width;++i)boundary[i]=family?0x1p10f:0x1p-28f;
        boundary[0]=family?0x1p50f:1.0f;
        double sums[2];unsigned fc[2];
        for(unsigned mode=0;mode<2;++mode) {
            const unsigned initial=rm<<5;
            asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0"::"r"(initial):"memory");
            sums[mode]=(mode?strict_candidate_rms_sum:strict_original_rms_sum)(boundary,width);
            fc[mode]=fcsr();errors+=vcsr()!=5 || vstart()!=0;
        }
        errors+=fc[0]!=fc[1] || std::memcmp(sums,sums+1,sizeof(double))!=0;++sum_checks;
    }
    printf("RMS_NORM_RESULT trials=8 outputs_checked=40960 boundary_cases=%u sum_cases=%u errors=%u\n",checks,sum_checks,errors);
    return errors?1:0;
}
