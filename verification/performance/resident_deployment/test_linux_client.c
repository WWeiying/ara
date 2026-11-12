#include "client.h"
#include "job_layout.h"
#include <asm/unistd.h>
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern long ara_resident_linux_execute_scalar(int, struct ara_resident_job *);
static unsigned calls, closes, info_mutation, output_flags, executions;
static long syscall_error;

long ara_resident_test_syscall(long nr, long a0, long a1, long a2)
{
    ++calls;
    if (nr == __NR_openat) return 9;
    if (nr == __NR_close) { assert(a0 == 9); ++closes; return 0; }
    assert(nr == __NR_ioctl && a0 == 9);
    if (a1 == ARA_RESIDENT_GET_INFO) {
        struct ara_resident_info *i = (void *)a2;
        *i = (struct ara_resident_info){.abi=1, .bytes=sizeof(*i), .features=3,
            .dimensions=7, .max_heads=8, .max_tokens=256, .nr_lanes=4, .vlen_bits=1024};
        switch (info_mutation) {
        case 1: i->abi = 2; break;
        case 2: --i->bytes; break;
        case 3: i->features |= 4; break;
        case 4: i->dimensions = 3; break;
        case 5: i->max_heads = 9; break;
        case 6: i->max_tokens = 257; break;
        case 7: i->nr_lanes = 8; break;
        case 8: i->vlen_bits = 512; break;
        case 9: i->reserved[3] = 1; break;
        }
    } else {
        assert(a1 == ARA_RESIDENT_EXECUTE);
        ++executions;
        ((struct ara_resident_job *)a2)->fflags = output_flags;
    }
    return syscall_error;
}

static struct ara_resident_job valid(void)
{
    return (struct ara_resident_job){.abi=1, .bytes=sizeof(struct ara_resident_job),
        .heads=2, .dimension=128, .tokens=128, .scale_bits=0x3d800000,
        .query=0x1000, .key=0x2000, .value=0x12000, .mask=0x22000, .output=0x24000};
}

int main(void)
{
    unsigned layouts = 0;
    struct ara_resident_sizes sizes;
    struct ara_resident_info info;
    _Static_assert(sizeof(struct ara_resident_info) == 64, "info ABI");
    _Static_assert(sizeof(struct ara_resident_job) == 104, "job ABI");
    _Static_assert(__builtin_offsetof(struct ara_resident_job, fflags) == 28, "assembly offset");
    for (unsigned heads=1; heads<=8; ++heads)
        for (unsigned dim=64; dim<=128; dim+=32)
            for (unsigned tokens=1; tokens<=256; ++tokens) {
                struct ara_resident_job j=valid();
                j.heads=heads; j.dimension=dim; j.tokens=tokens;
                assert(ara_resident_job_sizes(&j,&sizes));
                assert(sizes.query==heads*dim*2 && sizes.key==tokens*dim*2 &&
                    sizes.value==sizes.key && sizes.output==heads*dim*4 && sizes.mask==tokens*2);
                ++layouts;
            }
    for (unsigned mutation=0; mutation<19; ++mutation) {
        struct ara_resident_job j=valid();
        switch (mutation) {
        case 0: j.abi=0; break; case 1: --j.bytes; break;
        case 2: j.heads=0; break; case 3: j.heads=9; break;
        case 4: j.tokens=0; break; case 5: j.tokens=257; break;
        case 6: j.dimension=256; break; case 7: j.flags=1; break;
        case 8: j.fflags=1; break; case 9: j.scale_bits=0; break;
        case 10: j.scale_bits=0xbf800000; break; case 11: j.scale_bits=0x7f800000; break;
        case 12: j.scale_bits=0x7fc00000; break; case 13: j.query=0; break;
        case 14: j.key|=1; break; case 15: j.output|=2; break;
        case 16: j.reserved[3]=1; break; case 17: j.query=UINT64_MAX-1; break;
        case 18: j.output=UINT64_MAX-3; break;
        }
        assert(!ara_resident_job_sizes(&j,&sizes));
        unsigned before=calls;
        assert(ara_resident_linux_execute_scalar(9,&j)==-EINVAL && calls==before);
    }
    for (info_mutation=0; info_mutation<=9; ++info_mutation) {
        int fd=ara_resident_linux_open(&info);
        if (!info_mutation) { assert(fd==9); ara_resident_linux_close(fd); }
        else assert(fd==-EPROTO);
    }
    assert(closes==10);
    syscall_error=-ENODEV;
    assert(ara_resident_linux_open(&info)==-ENODEV && closes==11);
    for (unsigned pass=0; pass<4; ++pass) {
        struct ara_resident_job j=valid();
        const long errors[]={0,-EINTR,-EFAULT,-EOPNOTSUPP};
        syscall_error=errors[pass]; output_flags=5;
        unsigned before=executions;
        assert(ara_resident_linux_execute_scalar(9,&j)==errors[pass]);
        assert(executions==before+1); /* No automatic syscall replay. */
    }
    syscall_error=0; output_flags=32;
    struct ara_resident_job j=valid();
    assert(ara_resident_linux_execute_scalar(9,&j)==-EPROTO);
    puts("RESIDENT_LINUX_CLIENT_PASS layouts=6144 rejected=19 info_mutations=9 no_retry=4");
    assert(layouts==6144);
    return 0;
}
