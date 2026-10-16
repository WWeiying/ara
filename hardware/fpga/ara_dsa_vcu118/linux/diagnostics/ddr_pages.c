#define _GNU_SOURCE
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

/* Only ordinary allocated pages are touched, never /dev/mem or loader memory. */
int main(void) {
    const size_t bytes = 64UL << 20;
    long page = sysconf(_SC_PAGESIZE);
    uint64_t counts[2] = {0}, outside = 0;
    int fd = open("/proc/self/pagemap", O_RDONLY);
    uint64_t *p = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (page <= 0 || fd < 0 || p == MAP_FAILED) { perror("setup"); return 1; }
    if (mlock(p, bytes)) { perror("mlock"); return 1; }
    for (size_t i = 0; i < bytes / 8; ++i)
        p[i] = (UINT64_C(0x9e3779b97f4a7c15) * (i + 1)) ^ UINT64_C(0xa55a9876543210ef);
    for (size_t i = 0; i < bytes / 8; ++i) {
        uint64_t want = (UINT64_C(0x9e3779b97f4a7c15) * (i + 1)) ^ UINT64_C(0xa55a9876543210ef);
        if (((volatile uint64_t *)p)[i] != want) {
            printf("DATA_FAIL word=%zu\n", i); return 1;
        }
    }
    for (size_t i = 0; i < bytes; i += page) {
        uint64_t entry = 0;
        off_t off = (off_t)(((uintptr_t)p + i) / page) * 8;
        if (pread(fd, &entry, 8, off) != 8 || !(entry & (UINT64_C(1) << 63))) {
            fprintf(stderr, "PAGEMAP_FAIL offset=%zu\n", i); return 1;
        }
        uint64_t pa = (entry & ((UINT64_C(1) << 55) - 1)) * page;
        if (pa >= UINT64_C(0x80000000) && pa < UINT64_C(0xfeff0000)) counts[0]++;
        else if (pa >= UINT64_C(0x100000000) && pa < UINT64_C(0x180000000)) counts[1]++;
        else outside++;
    }
    printf("DDR_PAGES bytes=%zu page_size=%ld ddr1=%" PRIu64 " ddr2=%" PRIu64
           " outside=%" PRIu64 " data_verified=1\n", bytes, page, counts[0], counts[1], outside);
    munlock(p, bytes); munmap(p, bytes); close(fd);
    /* A data pass without DDR2 PFNs is not a dual-bank allocation proof. */
    return outside || !counts[1] ? 2 : 0;
}
