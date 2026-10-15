#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <setjmp.h>

static void host_store(void *, unsigned, uint64_t, unsigned);
static uint32_t host_lwu(const void *);
#include "case.c"

static unsigned call_number, event_count, lwu_count, inject_errors;
static const char *negative_mode;
static const char *variant;
static unsigned baseline, missing_nv_done;
static jmp_buf original_exit;
static int original_rc;
extern void original_probe_main(void);
extern void *original_area(unsigned);
long host_original_syscall3(long n,long x,long y,long z) {
    if(n==94){original_rc=(int)x;longjmp(original_exit,1);}
    return replay_write(n,x,y,z);
}
static char transcript[16384];
static unsigned transcript_length;
static struct { void *base; unsigned offset, width; } events[42];
static unsigned long equivalence_checks;

static void host_store(void *base, unsigned offset, uint64_t value, unsigned width) {
    assert(event_count < 41);
    if (negative_mode && !strcmp(negative_mode, "missing_input_store") && base == a && offset == 24)
        return;
    if (negative_mode && !strcmp(negative_mode, "missing_mask_store") && base == mask && offset == 120)
        return;
    if (negative_mode && !strcmp(negative_mode, "missing_output_tail") && base == output && offset == 128)
        return;
    events[event_count].base = base;
    events[event_count].offset = offset;
    events[event_count++].width = width;
    memcpy((unsigned char *)base + offset, &value, width);
}

static uint32_t host_lwu(const void *address) {
    uint32_t value;
    assert(address == output && !((uintptr_t)address & 3));
    memcpy(&value, address, sizeof(value));
    ++lwu_count;
    return value;
}

long replay_write(long n, long fd, long pointer, long length) {
    assert(n == 64 && fd == 1 && length >= 0);
    assert(transcript_length + (unsigned long)length < sizeof(transcript));
    memcpy(transcript + transcript_length, (const void *)pointer, length);
    transcript_length += length;
    transcript[transcript_length] = 0;
    return length;
}

unsigned long capacity(void) { return 16; }

static unsigned allowed_bit(unsigned op, unsigned seed, unsigned vl, unsigned i,
                            unsigned bitvalue, unsigned mode, unsigned *flags) {
    unsigned ai = (i + seed + 7 * (seed / 16)) % 16;
    unsigned bi = op < 4 ? (i * 3 + seed * 5 + seed / 16) % 16 : 14;
    struct fixture w = expected[op < 4 ? op : op - 4][ai][bi];
    unsigned old = (0x5b >> (i % 8)) & 1;
    if (i < vl && (((unsigned[]){255,170,36,0}[mode]>>(i%8))&1)) { *flags |= w.flags; return bitvalue == w.bit; }
    if (i < vl) return bitvalue == old;
    if (vl == 0) return bitvalue == old;
    return bitvalue == old || bitvalue == 1 || bitvalue == w.bit;
}

static unsigned original_errors(unsigned op, unsigned seed, unsigned vl,
                                unsigned mode, unsigned sticky, uint32_t value, uint64_t status) {
    unsigned errors = (uint32_t)status != 0, flags = sticky;
    for (unsigned i = 0; i < 16; ++i)
        errors += !allowed_bit(op, seed, vl, i, (value >> (i + 8)) & 1, mode, &flags);
    errors += (status >> 32) != flags;
    errors += (value & 255) != 91 || (value >> 24) != 91;
    return errors;
}

static unsigned long operate(unsigned op, const void *pa, const void *pb, void *pd,
                             unsigned long vl, unsigned long cap, const void *pm,
                             unsigned long start, unsigned long sticky) {
    const unsigned lengths[7] = {0, 1, 2, 3, 8, 15, 16};
    unsigned n = call_number, want_sticky = n % 2; n /= 2;
    unsigned mode = n % 4; n /= 4;
    unsigned li = n % 7; n /= 7;
    unsigned want_op = n % 10, seed = n / 10;
    assert(seed < 32 && op == want_op && vl == lengths[li] && cap == 16);
    assert(start == 0 && sticky == want_sticky);
    assert(pa == (baseline?original_area(0):(void *)a));
    assert(pb == (baseline?original_area(1):(void *)b));
    assert(pm == (baseline?original_area(2):(void *)mask));
    assert(pd == (unsigned char *)(baseline?original_area(3):(void *)output)+1);
    const word *aa=pa; word *bb=(word *)pb;
    const unsigned char *mm=pm; unsigned char *oo=(unsigned char *)pd-1;
    if(!baseline) {
    assert(event_count == 41);
    for (unsigned i = 0; i < 16; ++i) {
        assert(events[i].base == mask && events[i].offset == i * 8 && events[i].width == 8);
        assert(events[24+i].base == output && events[24+i].offset == i * 8 && events[24+i].width == 8);
    }
    for (unsigned i = 0; i < 4; ++i) {
        assert(events[16+2*i].base == a && events[16+2*i].offset == i*8 && events[16+2*i].width == 8);
        assert(events[17+2*i].base == b && events[17+2*i].offset == i*8 && events[17+2*i].width == 8);
    }
    assert(events[40].base == output && events[40].offset == 128 && events[40].width == 2);
    event_count = 0;
    }
    if (negative_mode && !strcmp(negative_mode, "wrong_raw_seed") && seed == 1 && op == 4) bb[0] = 0;
    for (unsigned i = 0; i < 16; ++i) {
        assert(aa[i] == inputs[(i+seed+7*(seed/16))%16]);
        assert(bb[i] == inputs[op < 4 ? (i*3+seed*5+seed/16)%16 : seed%16]);
    }
    for (unsigned i = 16; i < 1024; ++i) assert(aa[i] == 0 && bb[i] == 0);
    const unsigned char masks[4] = {255, 170, 36, 0};
    for (unsigned i = 0; i < 128; ++i) assert(mm[i] == masks[mode]);
    for (unsigned i = 0; i < 130; ++i) assert(oo[i] == 91);
    uint16_t value = 0;
    unsigned flags = sticky;
    for (unsigned i = 0; i < 16; ++i) {
        unsigned ai = (i+seed+7*(seed/16))%16;
        unsigned bi = op < 4 ? (i*3+seed*5+seed/16)%16 : 14;
        struct fixture w = expected[op < 4 ? op : op-4][ai][bi];
        unsigned active=i<vl && ((masks[mode]>>(i%8))&1);
        unsigned chosen=active?w.bit:(91>>(i%8))&1;
        if(variant && !strcmp(variant,"legal_tailones") && vl && i>=vl) chosen=1;
        value |= chosen << i;
        if(active) flags |= w.flags;
    }
    uint32_t observed = 91U | ((uint32_t)value << 8) | (91U << 24);
    uint64_t status = (uint64_t)flags << 32;
    uint64_t record = oracle_records[((seed*10+op)*7+li)*4+mode];
    if(negative_mode && !strcmp(negative_mode,"wrong_record_mode"))
        record=oracle_records[((seed*10+op)*7+li)*4+(mode+1)%4];
    assert(packed_errors(observed, status, record, flags) == 0);
    for (unsigned i = 0; i < 16; ++i) {
        uint32_t changed = observed ^ (1U << (i+8));
        assert(packed_errors(changed, status, record, flags) ==
               original_errors(op, seed, vl, mode, sticky, changed, status));
        ++equivalence_checks;
    }
    const uint32_t changes[] = {0x300, 1, 0x1000000, 0x1000001};
    for (unsigned i = 0; i < 4; ++i) {
        uint32_t changed = observed ^ changes[i];
        assert(packed_errors(changed, status, record, flags) ==
               original_errors(op, seed, vl, mode, sticky, changed, status));
        ++equivalence_checks;
    }
    const uint64_t status_changes[] = {1, UINT64_C(1)<<32, UINT64_C(16)<<32};
    for (unsigned i = 0; i < 3; ++i) {
        assert(packed_errors(observed, status ^ status_changes[i], record, flags) ==
               original_errors(op, seed, vl, mode, sticky, observed, status ^ status_changes[i]));
        ++equivalence_checks;
    }
    if (inject_errors && call_number < 21) value ^= 1;
    if(variant && !strcmp(variant,"alloff_spurious_NV") && seed==0 && op==0 && vl==8 && mode==3 && sticky==0) status^=UINT64_C(16)<<32;
    if(variant && !strcmp(variant,"active_missing_NV") && !missing_nv_done && (flags&16)) {status^=UINT64_C(16)<<32;missing_nv_done=1;}
    if(variant && !strcmp(variant,"inactive_result") && seed==0 && op==0 && vl==1 && mode==1 && sticky==0) value^=1;
    memcpy(pd, &value, 2);
    ++call_number;
    return status;
}

#define OP(N) unsigned long op_##N(const void *a,const void *b,void *c,unsigned long d, \
    unsigned long e,const void *f,unsigned long g,unsigned long h) { return operate(N,a,b,c,d,e,f,g,h); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)


int main(int argc,char **argv) {
    uint32_t endian=1;assert(*(unsigned char *)&endian==1 && argc==2);
    if(!strcmp(argv[1],"details")) inject_errors=1;
    else if(!strcmp(argv[1],"positive") || !strcmp(argv[1],"legal_tailones") ||
            !strcmp(argv[1],"alloff_spurious_NV") || !strcmp(argv[1],"active_missing_NV") ||
            !strcmp(argv[1],"inactive_result")) variant=argv[1];
    else negative_mode=argv[1];
    int rc=fp_compare_unboxed_masked_e16_mf4_full17920_main();
    assert(call_number==17920 && lwu_count==17920 && event_count==0);
    if(negative_mode) {fprintf(stderr,"NEGATIVE_NOT_REJECTED\n");return 3;}
    unsigned details=0;
    for(char *s=transcript;(s=strstr(s,"RVV_FP_COMPARE_DETAIL "));++s) ++details;
    if(inject_errors) {
        assert(rc==1 && details==20);
        assert(strstr(transcript,"RVV_FP_COMPARE_FAIL sew=16 cases=17920 errors=21\n"));
    } else if(!strcmp(variant,"alloff_spurious_NV") || !strcmp(variant,"active_missing_NV") || !strcmp(variant,"inactive_result")) {
        assert(rc==1 && details==1);
        assert(strstr(transcript,"cases=17920 errors=1\n"));
        if(!strcmp(variant,"alloff_spurious_NV")) assert(strstr(transcript,"op=0 seed=0 vl=8 mask=3 sticky=0 expected_flags=0 actual_flags=16 errors=1\n"));
    } else assert(rc==0 && details==0);
    char packed_transcript[sizeof(transcript)];strcpy(packed_transcript,transcript);
    baseline=1;call_number=0;transcript_length=0;transcript[0]=0;missing_nv_done=0;
    if(!setjmp(original_exit)) {original_probe_main();assert(!"original exit not intercepted");}
    assert(original_rc==rc && call_number==17920 && !strcmp(packed_transcript,transcript));
    printf("HOST_ORIGINAL_C_EQ_PASS mode=%s calls=17920 lwu=%u comparisons=%lu details=%u\n",argv[1],lwu_count,equivalence_checks,details);
    return 0;
}
