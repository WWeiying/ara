#include "kernel_compute.h"
#include <stdint.h>
#include <stddef.h>

extern const unsigned char capture_query[], capture_key[], capture_value[], capture_mask[];
extern const uint32_t expected_output[256], expected_flags;
static unsigned char scratch[32768] __attribute__((aligned(64)));
static struct {
    unsigned char before[64]; float data[256]; unsigned char after[64];
} output __attribute__((aligned(64)));

void *memcpy(void *destination, const void *source, size_t bytes)
{
    unsigned char *out=destination; const unsigned char *in=source;
    for (size_t i=0;i<bytes;++i) out[i]=in[i];
    return destination;
}
void *memset(void *destination, int value, size_t bytes)
{
    unsigned char *out=destination;
    for (size_t i=0;i<bytes;++i) out[i]=(unsigned char)value;
    return destination;
}
static void put(char c) { *(volatile unsigned char *)0xc0000000UL=(unsigned char)c; }
static void text(const char *s) { while (*s) put(*s++); }
static void hex(uint32_t value)
{
    const char digits[]="0123456789abcdef";
    for (int shift=28;shift>=0;shift-=4) put(digits[(value>>shift)&15]);
}
int main(void)
{
    struct ara_resident_compute_buffers b={
        .query=(void *)capture_query,.key=(void *)capture_key,
        .value=(void *)capture_value,.mask=(void *)capture_mask,
        .output=output.data,.scratch=scratch,.scratch_bytes=sizeof(scratch),
        .heads=2,.dimension=128,.tokens=65,.scale_bits=0x3db504f3,
        .flags=ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS,
    };
    memset(&output,0xa5,sizeof(output));
    unsigned errors=0;
    if (ara_resident_compute_scratch_bytes()>sizeof(scratch)) errors=1;
    int status=errors ? -22 : ara_resident_compute(&b);
    asm volatile("csrr zero,vl\nfence rw,rw" ::: "memory");
    for (unsigned i=0;i<256;++i) {
        uint32_t bits;
        memcpy(&bits,output.data+i,4);
        errors+=bits!=expected_output[i];
    }
    for (unsigned i=0;i<64;++i)
        errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    errors+=status!=0 || !b.started || !b.resident_used || b.flags!=expected_flags;
    text("RESIDENT_KERNEL_COMPUTE_RESULT status=");hex((uint32_t)status);
    text(" flags=");hex(b.flags);text(" errors=");hex(errors);put('\n');
    for (unsigned i=0;i<256;++i) {
        uint32_t bits;memcpy(&bits,output.data+i,4);
        text("RESIDENT_KERNEL_COMPUTE_OUTPUT index=");hex(i);text(" bits=");hex(bits);put('\n');
    }
    text(errors ? "RESIDENT_KERNEL_COMPUTE_FAIL\n" : "RESIDENT_KERNEL_COMPUTE_PASS\n");
    return errors!=0;
}
