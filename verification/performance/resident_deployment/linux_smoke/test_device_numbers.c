/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdio.h>
#include "device_numbers.h"

int main(void)
{
    static const unsigned minors[] = {0, 255, 256, 258, 1048575};
    static const char *bad[] = {"4096:258", "10:1048576", "10:", "10:-1", "10:258junk",
                                "99999999999999999999999:258"};
    dev_t dev;
    unsigned maj, min;
    for (unsigned i = 0; i < sizeof(minors) / sizeof(minors[0]); ++i) {
        assert(smoke_makedev(10, minors[i], &dev));
        assert(major(dev) == 10 && minor(dev) == minors[i]);
        printf("DEV_ROUNDTRIP major=10 minor=%u encoded=0x%lx PASS\n", minors[i], (unsigned long)dev);
    }
    assert(smoke_parse_device("10:258\n", &maj, &min, &dev));
    assert(maj == 10 && min == 258 && dev == (dev_t)0x00100a02);
    assert(smoke_makedev(0xfff, 0xfffff, &dev) && dev == (dev_t)0xffffffff);
    assert(!smoke_makedev(0x1000, 258, &dev));
    assert(!smoke_makedev(10, 0x100000, &dev));
    for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); ++i)
        assert(!smoke_parse_device(bad[i], &maj, &min, &dev));
    puts("DEVICE_NUMBERS_PASS roundtrips=5 actual_10_258=0x100a02 bounds=PASS malformed=6");
    return 0;
}
