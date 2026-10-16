#include "eth_loader_ddr.h"

#include "xparameters.h"

#include <stdint.h>

#if defined(XPAR_MICROBLAZE_USE_DCACHE) && XPAR_MICROBLAZE_USE_DCACHE
#error "DDR readback requires the validated cache-disabled MicroBlaze configuration"
#endif

static int allowed(uint64_t address, size_t size) {
    return address >= ETH_LOADER_DDR_START &&
           address < ETH_LOADER_DDR_LIMIT &&
           size <= ETH_LOADER_DDR_LIMIT - address;
}

static int write_ddr(void *context, uint64_t address, const void *data, size_t size) {
    volatile uint8_t *destination;
    const uint8_t *source = data;
    (void)context;
    if (!data || !allowed(address, size)) return -1;
    destination = (volatile uint8_t *)(uintptr_t)address;
    if ((((uintptr_t)destination | (uintptr_t)source) & 3u) == 0) {
        volatile uint32_t *destination_words = (volatile uint32_t *)destination;
        const uint32_t *source_words = (const uint32_t *)source;
        size_t words = size / sizeof(uint32_t);
        for (size_t i = 0; i < words; ++i)
            destination_words[i] = source_words[i];
        for (size_t i = words * sizeof(uint32_t); i < size; ++i)
            destination[i] = source[i];
    } else {
        for (size_t i = 0; i < size; ++i) destination[i] = source[i];
    }
    return 0;
}

static int readback_crc32(void *context, uint64_t address, size_t size, uint32_t *result) {
    const volatile uint8_t *source;
    uint32_t crc = UINT32_MAX;
    (void)context;
    if (!result || !allowed(address, size)) return -1;
    source = (const volatile uint8_t *)(uintptr_t)address;
    size_t i = 0;
#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__) && \
    __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    while (i < size && ((address + i) & 3u))
        crc = eth_loader_crc32_byte(crc, source[i++]);
    while (size - i >= sizeof(uint32_t)) {
        uint32_t word = *(const volatile uint32_t *)(source + i);
        crc = eth_loader_crc32_word(crc, word);
        i += sizeof(uint32_t);
    }
#endif
    for (; i < size; ++i)
        crc = eth_loader_crc32_byte(crc, source[i]);
    *result = ~crc;
    return 0;
}

const struct eth_loader_io eth_loader_ddr_io = {
    NULL, NULL, write_ddr, readback_crc32
};
