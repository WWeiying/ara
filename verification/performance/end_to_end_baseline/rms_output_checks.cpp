#include "rms_output.h"
#include "printf.h"
#include <cstring>

alignas(64) static float arena[2][640];

static unsigned fcsr() {
    unsigned value;
    asm volatile("frcsr %0" : "=r"(value) :: "memory");
    return value;
}
static bool vector_state() {
    unsigned vc, vs;
    asm volatile("csrr %0,vcsr;csrr %1,vstart" : "=r"(vc), "=r"(vs) :: "memory");
    return vc == 5 && vs == 0;
}
static __attribute__((noinline, optimize("no-tree-vectorize", "no-tree-slp-vectorize")))
void scalar_output(float *y, const float *x, const float *w, float scale, size_t n) {
    for (size_t i=0; i<n; ++i) {
        volatile float normalized = x[i]*scale;
        y[i] = normalized*w[i];
    }
}

static float from_bits(uint32_t bits) {
    float value;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

static uint32_t case_digest(uint32_t hash, const float *values, unsigned flags,
                            unsigned mode, unsigned width, unsigned rm) {
    for (unsigned i=0; i<640; ++i) {
        uint32_t word;
        std::memcpy(&word, values+i, sizeof(word));
        hash=(hash^word)*16777619u;
    }
    const uint32_t metadata[]={flags,mode,width,rm};
    for (uint32_t word:metadata) hash=(hash^word)*16777619u;
    return hash;
}

struct OutputPattern {
    uint32_t scale;
    uint32_t input[8];
    uint32_t weight[8];
};

// Raw loads preserve signaling NaNs and payloads until the tested multiplies.
static const OutputPattern ieee_patterns[] = {
    // Positive and negative zero in all three operand positions.
    {0x00000000u,
     {0x00000000u,0x80000000u,0x3f800000u,0xbf800000u,0x00000001u,0x80000001u,0x00800000u,0x80800000u},
     {0x3f800000u,0xbf800000u,0x80000000u,0x00000000u,0xbf800000u,0x3f800000u,0x40000000u,0xc0000000u}},
    {0x80000000u,
     {0x80000000u,0x00000000u,0xbf800000u,0x3f800000u,0x80000001u,0x00000001u,0x80800000u,0x00800000u},
     {0xbf800000u,0x3f800000u,0x00000000u,0x80000000u,0x3f800000u,0xbf800000u,0xc0000000u,0x40000000u}},
    // Quiet/signaling NaNs in scale, input and weight, with distinct payloads.
    {0x7fc12345u,
     {0x3f800000u,0x7fc23456u,0xffc34567u,0x7f812345u,0x00000000u,0x7f800000u,0xff800000u,0x00000001u},
     {0xffc45678u,0x3f800000u,0x7f823456u,0xbf800000u,0x80000000u,0x40000000u,0x00000001u,0x7fc56789u}},
    {0x7f812345u,
     {0x7f823456u,0xff834567u,0x7fc45678u,0x3f800000u,0x80000000u,0xff800000u,0x00800000u,0xbf800000u},
     {0x3f800000u,0x7fc56789u,0xff845678u,0x7f856789u,0x00000000u,0x40000000u,0x00000001u,0xffc6789au}},
    // Invalid Inf*0 in the first multiply and Inf*0 in the second multiply.
    {0x7f800000u,
     {0x00000000u,0x80000000u,0x3f800000u,0xbf800000u,0x7f800000u,0xff800000u,0x00000001u,0x80000001u},
     {0x3f800000u,0xbf800000u,0x00000000u,0x80000000u,0x40000000u,0xc0000000u,0xff800000u,0x7f800000u}},
    {0xff800000u,
     {0x80000000u,0x00000000u,0xbf800000u,0x3f800000u,0xff800000u,0x7f800000u,0x80000001u,0x00000001u},
     {0xbf800000u,0x3f800000u,0x80000000u,0x00000000u,0xc0000000u,0x40000000u,0x7f800000u,0xff800000u}},
    // Halfway subnormals and underflow before/after the second multiply.
    {0x3f000000u,
     {0x00000001u,0x80000001u,0x00000003u,0x80000003u,0x00800000u,0x80800000u,0x007fffffu,0x807fffffu},
     {0x40000000u,0x40000000u,0x3f000000u,0x3f000000u,0x00000001u,0x80000001u,0x00800000u,0x80800000u}},
    // Overflow before a compensating weight; reassociation would hide it.
    {0x40000000u,
     {0x7f7fffffu,0xff7fffffu,0x7f000000u,0xff000000u,0x3f800000u,0xbf800000u,0x00800000u,0x80800000u},
     {0x3f000000u,0x3f000000u,0x00000000u,0x80000000u,0x7f7fffffu,0xff7fffffu,0x00000001u,0x80000001u}},
    // Subnormal scale, with both exact and inexact tiny products.
    {0x00000001u,
     {0x3f800000u,0xbf800000u,0x3f000000u,0xbf000000u,0x7f7fffffu,0xff7fffffu,0x00800000u,0x80800000u},
     {0x3f800000u,0xbf800000u,0x40000000u,0x40000000u,0x00000001u,0x80000001u,0x7f7fffffu,0xff7fffffu}},
    // Finite maximal scale and weights exercise both overflow sites.
    {0x7f7fffffu,
     {0x40000000u,0xc0000000u,0x3f800000u,0xbf800000u,0x00000001u,0x80000001u,0x3f000000u,0xbf000000u},
     {0x3f000000u,0x3f000000u,0x40000000u,0xc0000000u,0x7f7fffffu,0xff7fffffu,0x00000001u,0x80000001u}},
    // RNE lane 0: (x*s)*w=0x3f7ffff1, x*(s*w)=0x3f7ffff0.
    {0x3f800001u,
     {0x3f7ffff0u,0xbf7ffff0u,0x3f800001u,0xbf800001u,0x3f7fffffu,0xbf7fffffu,0x3f800003u,0xbf800003u},
     {0x3f7fffffu,0x3f7fffffu,0x3f800001u,0x3f800001u,0x3f800003u,0xbf800003u,0x3f7ffffdu,0xbf7ffffdu}},
    {0x3f7fffffu,
     {0x3f800001u,0xbf800001u,0x3f7fffffu,0xbf7fffffu,0x00800000u,0x80800000u,0x7f7fffffu,0xff7fffffu},
     {0x3f800003u,0x3f800003u,0x3f7ffffdu,0x3f7ffffdu,0x3f000000u,0x3f000000u,0x3f800001u,0x3f800001u}},
};
static_assert(sizeof(ieee_patterns)/sizeof(ieee_patterns[0]) == 12, "IEEE output pattern count");

extern "C" unsigned rms_output_checks() {
    unsigned errors=0, cases=0, fast=0, fallback=0, empty=0;
    uint32_t digest=2166136261u;
    const unsigned widths[] = {33, 129};
    for (unsigned rm=0; rm<5; ++rm) {
        for (unsigned width:widths) for (unsigned mode=0; mode<9; ++mode) {
            for (unsigned i=0; i<640; ++i) arena[0][i] = (int(i%257)-128)*0.0137f;
            std::memcpy(arena[1], arena[0], sizeof(arena[0]));
            unsigned x=16, w=192, y=384;
            if (mode==1) y=x;
            if (mode==2) y=w;
            if (mode==3) y=x+1;
            if (mode==4) y=x-1;
            if (mode==5) y=w+1;
            if (mode==6) y=w-1;
            if (mode==7) w=x;
            if (mode==8) y=w=x;
            const unsigned initial=(rm<<5)|8;
            asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0" :: "r"(initial) : "memory");
            scalar_output(arena[0]+y, arena[0]+x, arena[0]+w, 0x1.000002p+0f, width);
            const bool scalar_state_ok=vector_state();
            const unsigned expected_flags=fcsr();
            errors += !scalar_state_ok || (expected_flags & ~31u)!=(rm<<5) || !(expected_flags & 8u);
            asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0" :: "r"(initial) : "memory");
            const bool selected=ggml_rvv_fused_rms_output(arena[1]+y, arena[1]+x, arena[1]+w,
                                                        0x1.000002p+0f, width);
            if (!selected) scalar_output(arena[1]+y, arena[1]+x, arena[1]+w, 0x1.000002p+0f, width);
            const bool candidate_state_ok=vector_state();
            const unsigned actual_flags=fcsr();
            errors += actual_flags!=expected_flags || !candidate_state_ok ||
                      std::memcmp(arena[0], arena[1], sizeof(arena[0]))!=0;
            errors += selected != (mode<3 || mode==7 || mode==8);
            digest=case_digest(digest, arena[1], actual_flags, mode, width, rm);
            ++cases; fast+=selected; fallback+=!selected;
        }
        unsigned ieee_mode=9;
        for (const OutputPattern &pattern:ieee_patterns) {
            for (unsigned i=0; i<640; ++i) {
                const uint32_t guard=0xa5a50000u+i;
                std::memcpy(&arena[0][i], &guard, sizeof(guard));
            }
            for (unsigned i=0; i<129; ++i) {
                std::memcpy(&arena[0][16+i], &pattern.input[i%8], sizeof(float));
                std::memcpy(&arena[0][192+i], &pattern.weight[i%8], sizeof(float));
            }
            std::memcpy(arena[1], arena[0], sizeof(arena[0]));
            const float scale=from_bits(pattern.scale);
            const unsigned initial=(rm<<5)|8;
            asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0" :: "r"(initial) : "memory");
            scalar_output(arena[0]+384, arena[0]+16, arena[0]+192, scale, 129);
            const bool scalar_state_ok=vector_state();
            const unsigned expected_flags=fcsr();
            errors += !scalar_state_ok || (expected_flags & ~31u)!=(rm<<5) || !(expected_flags & 8u);
            asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0" :: "r"(initial) : "memory");
            const bool selected=ggml_rvv_fused_rms_output(arena[1]+384, arena[1]+16,
                                                        arena[1]+192, scale, 129);
            if (!selected) scalar_output(arena[1]+384, arena[1]+16, arena[1]+192, scale, 129);
            const bool candidate_state_ok=vector_state();
            const unsigned actual_flags=fcsr();
            errors += !selected || actual_flags!=expected_flags || !candidate_state_ok ||
                      std::memcmp(arena[0], arena[1], sizeof(arena[0]))!=0;
            uint32_t scale_bits;
            std::memcpy(&scale_bits, &scale, sizeof(scale_bits));
            errors += scale_bits!=pattern.scale;
            digest=case_digest(digest, arena[1], actual_flags, ieee_mode++, 129, rm);
            ++cases; fast+=selected; fallback+=!selected;
        }
        const unsigned initial=(rm<<5)|8;
        asm volatile("fscsr %0;csrwi vcsr,5;csrwi vstart,0" :: "r"(initial) : "memory");
        const bool selected=ggml_rvv_fused_rms_output(nullptr, nullptr, nullptr, 1.0f, 0);
        const bool empty_state_ok=vector_state();
        const unsigned actual_flags=fcsr();
        errors += !selected || actual_flags!=initial || !empty_state_ok;
        digest=case_digest(digest, arena[1], actual_flags, 21, 0, rm);
        ++cases; ++empty;
    }
    errors += cases!=155 || fast!=110 || empty!=5 || fallback!=40;
    printf("RMS_OUTPUT_CHECK cases=%u vector_calls=%u empty_calls=%u scalar_fallbacks=%u digest=%u errors=%u\n",
           cases, fast, empty, fallback, digest, errors);
    return errors;
}
