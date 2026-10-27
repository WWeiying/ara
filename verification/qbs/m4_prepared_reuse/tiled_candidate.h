#pragma once

#include "q8_K-m4.h"

namespace m4_tiled_candidate {

#if GGML_RISCV_Q8_K_M4_VECTOR
inline vint8m1_t encode(const float *input,float scale,size_t vl) {
    const auto x=__riscv_vle32_v_f32m4(input,vl);
    const auto bias=__riscv_vfmv_v_f_f32m4(12582912.0f,vl);
    const auto biased=__riscv_vfmacc_vf_f32m4(bias,scale,x,vl);
    auto bits=__riscv_vreinterpret_v_f32m4_i32m4(biased);
    bits=__riscv_vand_vx_i32m4(bits,0x007fffff,vl);
    bits=__riscv_vsub_vx_i32m4(bits,0x00400000,vl);
    return __riscv_vncvt_x_x_w_i8m1(__riscv_vncvt_x_x_w_i16m2(bits,vl),vl);
}

inline void sums(vint8m1_t q,int16_t *destination,size_t vl) {
    for(size_t first=0;first<vl;first+=16) {
        const auto group=__riscv_vslidedown_vx_i8m1(q,first,16);
        const auto zero=__riscv_vmv_v_x_i16m1(0,1);
        const auto sum=__riscv_vwredsum_vs_i8m1_i16m1(group,zero,16);
        destination[(first/16)*4]=__riscv_vmv_x_s_i16m1_i16(sum);
    }
}
#endif

// Verification-only candidate. The original producer and numerical/fallback
// contract remain unchanged. Segment stores emit the existing four-row layout.
inline bool quantize(const float *GGML_RESTRICT x,void *GGML_RESTRICT output,int64_t k) {
    static_assert(QK_K==256,"native block layout changed");
    assert(k>=0 && k%QK_K==0 && k/QK_K<=INT_MAX);
#if GGML_RISCV_Q8_K_M4_VECTOR
    unsigned frm;asm volatile("frrm %0":"=r"(frm)::"memory");
    const size_t span=__riscv_vsetvl_e32m4(128);
    if(frm || !k || span<16 || span%16 || !ggml_riscv_q8_K_m4::vector_domain(x,k)) {
        ggml_quantize_mat_q8_K_4x1_ara_generic(x,output,k);return false;
    }
    auto *y=static_cast<block_q8_Kx4 *>(output);
    for(int64_t b=0;b<k/QK_K;++b) {
        float scale[4];
        for(int row=0;row<4;++row) {
            float absolute;
            const float maximum=ggml_riscv_q8_K_signed_max(x+row*k+b*QK_K,QK_K,&absolute);
            scale[row]=absolute ? -127.0f/maximum:0.0f;
            y[b].d[row]=absolute ? 1.0f/scale[row]:0.0f;
        }
        for(size_t first=0;first<QK_K;first+=span) {
            const size_t vl=__riscv_vsetvl_e32m4(span);
            const auto q0=encode(x+b*QK_K+first,scale[0],vl);
            sums(q0,y[b].bsums+4*(first/16),vl);
            const auto q1=encode(x+k+b*QK_K+first,scale[1],vl);
            sums(q1,y[b].bsums+4*(first/16)+1,vl);
            const auto q2=encode(x+2*k+b*QK_K+first,scale[2],vl);
            sums(q2,y[b].bsums+4*(first/16)+2,vl);
            const auto q3=encode(x+3*k+b*QK_K+first,scale[3],vl);
            sums(q3,y[b].bsums+4*(first/16)+3,vl);
            auto packed=__riscv_vundefined_i8m1x4();
            packed=__riscv_vset_v_i8m1_i8m1x4(packed,0,q0);
            packed=__riscv_vset_v_i8m1_i8m1x4(packed,1,q1);
            packed=__riscv_vset_v_i8m1_i8m1x4(packed,2,q2);
            packed=__riscv_vset_v_i8m1_i8m1x4(packed,3,q3);
            __riscv_vsseg4e8_v_i8m1x4(y[b].qs+4*first,packed,vl);
        }
    }
    return true;
#else
    ggml_quantize_mat_q8_K_4x1_ara_generic(x,output,k);return false;
#endif
}

} // namespace m4_tiled_candidate
