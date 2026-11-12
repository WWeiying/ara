#include "client.h"
#include <stdint.h>

static unsigned calls;
static long code;
long ara_resident_linux_execute_scalar(int fd, struct ara_resident_job *job)
{
    (void)fd;
    ++calls;
    job->fflags=5;
    asm volatile("csrwi fcsr,0;csrwi vcsr,0" ::: "memory");
    return code;
}
static unsigned csr(unsigned which)
{
    unsigned long value;
    if (!which) asm volatile("frcsr %0":"=r"(value));
    else if (which==1) asm volatile("csrr %0,vcsr":"=r"(value));
    else asm volatile("csrr %0,vstart":"=r"(value));
    return value;
}
int main(void)
{
    struct ara_resident_job job={0};
    asm volatile("li t0,48;csrw fcsr,t0;csrwi vcsr,7" ::: "t0","memory");
    if (ara_resident_linux_execute(9,&job) || csr(0)!=53 || csr(1)!=7 || csr(2)) return 1;
    code=-5;
    asm volatile("csrwi fcsr,8;csrwi vcsr,6" ::: "memory");
    if (ara_resident_linux_execute(9,&job)!=-5 || csr(0)!=8 || csr(1)!=6 || csr(2)) return 2;
    asm volatile("csrwi vstart,3" ::: "memory");
    if (ara_resident_linux_execute(9,&job)!=-34 || csr(0)!=8 || csr(1)!=6 || csr(2)!=3 || calls!=2) return 3;
    asm volatile("csrwi vstart,0" ::: "memory");
    return 0;
}
