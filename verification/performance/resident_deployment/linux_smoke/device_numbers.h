/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RESIDENT_SMOKE_DEVICE_NUMBERS_H
#define RESIDENT_SMOKE_DEVICE_NUMBERS_H

#include <sys/types.h>
#include <sys/sysmacros.h>

static inline int smoke_makedev(unsigned maj, unsigned min, dev_t *out)
{
    dev_t dev;
    if (!out || maj > 0xfffU || min > 0xfffffU) return 0;
    dev = makedev(maj, min);
    if (major(dev) != maj || minor(dev) != min || dev > 0xffffffffUL) return 0;
    *out = dev;
    return 1;
}

static inline int smoke_decimal(const char **input, unsigned maximum, unsigned *out)
{
    const char *s = *input;
    unsigned value = 0;
    if (*s < '0' || *s > '9') return 0;
    while (*s >= '0' && *s <= '9') {
        unsigned digit = *s++ - '0';
        if (value > (maximum - digit) / 10) return 0;
        value = value * 10 + digit;
    }
    *input = s;
    *out = value;
    return 1;
}

static inline int smoke_parse_device(const char *s, unsigned *maj, unsigned *min, dev_t *out)
{
    if (!smoke_decimal(&s, 0xfffU, maj) || *s++ != ':' ||
        !smoke_decimal(&s, 0xfffffU, min)) return 0;
    if (*s == '\n') ++s;
    return !*s && smoke_makedev(*maj, *min, out);
}

#endif
