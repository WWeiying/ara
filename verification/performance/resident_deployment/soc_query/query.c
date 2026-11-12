#include "akv/akv.h"
#include "printf.h"

static uint64_t words[5];

static uint64_t actual_info(uint64_t index) {
  uint64_t result;
  __asm__ volatile(".insn r 0x5b, 4, 0, %0, %1, x0"
                   : "=r"(result) : "r"(index) : "memory");
  return result;
}

static uint64_t captured_info(void *context, unsigned index) {
  (void)context;
  return words[index];
}

int main(void) {
  static const uint64_t expected[5] = {
      UINT64_C(0x000f010808400101), UINT64_C(0x00000000006b1a5b),
      UINT64_C(0x000001ff06084002), UINT64_C(0x0000000001803e5b),
      UINT64_C(0x0000040000040301),
  };
  unsigned errors = 0;
  for (unsigned index = 0; index < 5; ++index) {
    words[index] = actual_info(index);
    errors += words[index] != expected[index];
  }
  errors += actual_info(5) != 0;
  errors += actual_info(UINT64_C(0x100000004)) != 0;
  akv_device_t device;
  const akv_status_t status = akv_device_query(captured_info, 0, &device);
  errors += status != AKV_STATUS_OK;
  errors += !device.capabilities.valid || !device.capabilities.token_axis_valid;
  errors += !device.capabilities.resident_valid || !device.capabilities.resident_pv_supported ||
            !device.capabilities.resident_qk_supported;
  errors += device.capabilities.resident_capability_version != 1 ||
            device.capabilities.resident_nr_lanes != 4 ||
            device.capabilities.resident_vlen_bits != 1024;
  printf("RESIDENT_QUERY info0=%016lx info1=%016lx info2=%016lx info3=%016lx info4=%016lx "
         "status=%u valid=%u pv=%u qk=%u lanes=%u vlen=%u errors=%u\n",
         (unsigned long)words[0], (unsigned long)words[1], (unsigned long)words[2],
         (unsigned long)words[3], (unsigned long)words[4], status,
         device.capabilities.resident_valid, device.capabilities.resident_pv_supported,
         device.capabilities.resident_qk_supported, device.capabilities.resident_nr_lanes,
         device.capabilities.resident_vlen_bits, errors);
  return errors != 0;
}
