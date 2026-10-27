#include "printf.h"
#include <cstdint>
#include <cstring>

extern "C" bool m4_produce(const float *,void *,int64_t);
extern "C" bool m4_tiled_produce(const float *,void *,int64_t);
extern "C" const float projection_input[];
extern "C" const unsigned char projection_golden[],projection_input_copy[];
alignas(64) static unsigned char output[3][7008+128];
static uint64_t cycles() {uint64_t x;asm volatile("fence rw,rw;rdcycle %0":"=r"(x)::"memory");return x;}
int main() {
    unsigned errors=std::memcmp(projection_input,projection_input_copy,24576)!=0;
    for(unsigned trial=0;trial<4;++trial) {
        const bool tiled=trial==1 || trial==2;
        std::memset(output,0xa5,sizeof(output));
        asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0"::"r"(17):"memory");
        uint64_t points[4];unsigned flags[3],vector_flags[3];bool used=true;
        points[0]=cycles();
        for(unsigned call=0;call<3;++call) {
            used&=tiled ? m4_tiled_produce(projection_input,output[call]+64,1536):
                         m4_produce(projection_input,output[call]+64,1536);
            asm volatile("frcsr %0;csrr %1,vcsr":"=r"(flags[call]),"=r"(vector_flags[call])::"memory");
            points[call+1]=cycles();
        }
        unsigned local=!used;
        for(unsigned call=0;call<3;++call) {
            local+=flags[call]!=17 || vector_flags[call]!=5 ||
                   std::memcmp(output[call]+64,projection_golden,7008)!=0;
            for(unsigned i=0;i<64;++i) local+=output[call][i]!=0xa5 || output[call][7072+i]!=0xa5;
        }
        errors+=local;
        printf("M4_TILED_TRIAL id=%u tiled=%u first=%lu second=%lu third=%lu total=%lu errors=%u\n",
            trial,unsigned(tiled),(unsigned long)(points[1]-points[0]),(unsigned long)(points[2]-points[1]),
            (unsigned long)(points[3]-points[2]),(unsigned long)(points[3]-points[0]),local);
    }
    errors+=std::memcmp(projection_input,projection_input_copy,24576)!=0;
    printf("M4_TILED_RESULT errors=%u trials=4 calls=12 m=4 k=1536\n",errors);
    return errors ? 1:0;
}
