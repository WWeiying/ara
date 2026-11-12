#include "akv/akv.h"

#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static const uint64_t native_words[4] = {
    UINT64_C(0x000f010808400101), UINT64_C(0x00000000006b1a5b),
    UINT64_C(0x000001ff06084002), UINT64_C(0x0000000001803e5b),
};
static const uint64_t pv_word = UINT64_C(0x0000040000040101);
static const uint64_t both_word = UINT64_C(0x0000040000040301);

typedef struct {
  uint64_t words[5];
  unsigned next;
} reader_context_t;

static uint64_t read_info(void *opaque, unsigned index) {
  reader_context_t *context = opaque;
  assert(index < 5u && index == context->next++);
  return context->words[index];
}

static akv_capabilities_t native_caps(void) {
  akv_capabilities_t caps;
  assert(akv_capabilities_decode_extended(native_words[0], native_words[1],
      native_words[2], native_words[3], &caps) == AKV_STATUS_OK);
  return caps;
}

static void assert_resident_off(const akv_capabilities_t *caps) {
  assert(!caps->resident_valid && !caps->resident_pv_supported &&
         !caps->resident_qk_supported && !caps->resident_capability_version &&
         !caps->resident_nr_lanes && !caps->resident_vlen_bits);
}

static void assert_native_equal(const akv_capabilities_t *a,
                                const akv_capabilities_t *b) {
  assert(memcmp(a, b, offsetof(akv_capabilities_t, resident_valid)) == 0);
}

static void check_word(uint64_t word, akv_status_t expected) {
  akv_capabilities_t caps = native_caps();
  const akv_capabilities_t baseline = caps;
  assert(akv_capabilities_decode_resident(both_word, &caps) == AKV_STATUS_OK);
  assert(akv_capabilities_decode_resident(word, &caps) == expected);
  assert_native_equal(&caps, &baseline);
  if (expected == AKV_STATUS_OK) {
    assert(caps.resident_valid && caps.resident_pv_supported);
    assert(caps.resident_qk_supported == (word == both_word));
    assert(caps.resident_capability_version == 1u);
    assert(caps.resident_nr_lanes == 4u && caps.resident_vlen_bits == 1024u);
  } else {
    assert_resident_off(&caps);
  }

  reader_context_t reader = {.words = {0}, .next = 0};
  memcpy(reader.words, native_words, sizeof(native_words));
  reader.words[4] = word;
  akv_device_t device;
  assert(akv_device_query(read_info, &reader, &device) == AKV_STATUS_OK);
  assert(reader.next == 5u);
  assert(memcmp(&caps, &device.capabilities, sizeof(caps)) == 0);
}

static void check_abi_and_malformed(void) {
  for (unsigned index = 0; index < 8u; ++index) {
    for (unsigned enabled = 0; enabled < 2u; ++enabled) {
      const uint64_t old = akv_capability_word(index, (int)enabled) |
                           akv_v2_capability_word(index, (int)enabled);
      uint64_t expected = index < 4u ? native_words[index] : 0u;
      if (!enabled && index == 0u) expected &= ~(UINT64_C(1) << 48);
      if (!enabled && index == 2u) expected &= ~(UINT64_C(1) << 32);
      assert(old == expected);
      assert(akv_resident_pv_capability_word(index, (int)enabled) ==
             (index == 4u && enabled ? pv_word : 0u));
      assert(akv_resident_qk_capability_word(index, (int)enabled) ==
             (index == 4u && enabled ? both_word & ~UINT64_C(0x100) : 0u));
    }
  }
  assert(!akv_resident_pv_capability_word(UINT64_MAX, 1));
  assert(!akv_resident_qk_capability_word(UINT64_C(0x100000004), 1));
  assert(!akv_resident_pv_is_supported() && !akv_resident_qk_is_supported());
  check_word(0u, AKV_STATUS_RUNTIME_UNAVAILABLE);
  check_word(pv_word, AKV_STATUS_OK);
  check_word(both_word, AKV_STATUS_OK);
  check_word(AKV_RESIDENT_CAPABILITY_BASE_WORD, AKV_STATUS_ABI_MISMATCH);
  check_word(both_word & ~UINT64_C(0x100), AKV_STATUS_ABI_MISMATCH);
  check_word(UINT64_MAX, AKV_STATUS_ABI_MISMATCH);
  for (unsigned bit = 0; bit < 64u; ++bit)
    check_word(both_word ^ (UINT64_C(1) << bit),
               bit == 9u ? AKV_STATUS_OK : AKV_STATUS_ABI_MISMATCH);
  for (unsigned version = 0; version < 256u; ++version)
    check_word((both_word & ~UINT64_C(0xff)) | version,
               version == 1u ? AKV_STATUS_OK : AKV_STATUS_ABI_MISMATCH);
  for (unsigned lanes = 0; lanes < 256u; ++lanes)
    check_word((both_word & ~UINT64_C(0xff0000)) | ((uint64_t)lanes << 16),
               lanes == 4u ? AKV_STATUS_OK : AKV_STATUS_ABI_MISMATCH);
  for (unsigned vlen = 0; vlen < 65536u; ++vlen)
    check_word((both_word & ~UINT64_C(0xffff00000000)) | ((uint64_t)vlen << 32),
               vlen == 1024u ? AKV_STATUS_OK : AKV_STATUS_ABI_MISMATCH);
}

static void check_dependencies(void) {
  akv_capabilities_t caps;
  assert(akv_capabilities_decode_resident(both_word, NULL) == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_device_query(NULL, NULL, NULL) == AKV_STATUS_BAD_ARGUMENT);
  for (unsigned missing = 0; missing < 5u; ++missing) {
    caps = native_caps();
    if (missing == 0u) caps.valid = 0u;
    if (missing == 1u) caps.enabled = 0u;
    if (missing == 2u) caps.token_axis_valid = 0u;
    if (missing == 3u) caps.token_axis_enabled = 0u;
    if (missing == 4u) caps.f16_payload = 0u;
    const akv_capabilities_t baseline = caps;
    assert(akv_capabilities_decode_resident(both_word, &caps) == AKV_STATUS_CAPABILITY);
    assert_native_equal(&caps, &baseline);
    assert_resident_off(&caps);
  }
  assert(akv_capabilities_decode_extended(native_words[0], native_words[1],
                                         0u, 0u, &caps) == AKV_STATUS_OK);
  assert(akv_capabilities_decode_resident(both_word, &caps) == AKV_STATUS_CAPABILITY);
  assert(caps.valid && caps.enabled);
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  assert_resident_off(&device.capabilities);
  caps = native_caps();
  assert(akv_capabilities_decode_resident(both_word, &caps) == AKV_STATUS_OK);
  assert(akv_capabilities_decode(native_words[0], native_words[1], &caps) == AKV_STATUS_OK);
  assert_resident_off(&caps);

  for (unsigned bad = 0; bad < 4u; ++bad) {
    reader_context_t reader = {.words = {0}, .next = 0};
    memcpy(reader.words, native_words, sizeof(native_words));
    reader.words[4] = both_word;
    if (bad == 0u) reader.words[0] = 0u;
    if (bad == 1u) reader.words[1] ^= 1u;
    if (bad == 2u) reader.words[2] ^= UINT64_C(1) << 63;
    if (bad == 3u) reader.words[3] = 0u;
    assert(akv_device_query(read_info, &reader, &device) != AKV_STATUS_OK);
    assert_resident_off(&device.capabilities);
  }
}

/* Consume words emitted by the real SV package and extracted dispatcher gates. */
static void check_sv_vectors(const char *path) {
  FILE *file = fopen(path, "r");
  assert(file != NULL);
  unsigned lanes, vlen, fpu, flags, count = 0;
  reader_context_t reader;
  while (fscanf(file, "%u %u %u %u %" SCNx64 " %" SCNx64 " %" SCNx64
               " %" SCNx64 " %" SCNx64,
               &lanes, &vlen, &fpu, &flags, &reader.words[0], &reader.words[1],
               &reader.words[2], &reader.words[3], &reader.words[4]) == 9) {
    const int native = (flags & 1u) && lanes == 4u && vlen == 1024u;
    const int v2 = native && (flags & 2u);
    const int pv = v2 && (flags & 4u) && (fpu & 8u);
    const int qk = pv && (flags & 8u) && (fpu & 16u);
    assert(reader.words[4] == (pv ? (qk ? both_word : pv_word) : 0u));
    reader.next = 0u;
    akv_device_t device;
    assert(akv_device_query(read_info, &reader, &device) ==
           (native ? AKV_STATUS_OK : AKV_STATUS_RUNTIME_UNAVAILABLE));
    assert(reader.next == 5u);
    assert(device.capabilities.resident_valid == pv);
    assert(device.capabilities.resident_pv_supported == pv);
    assert(device.capabilities.resident_qk_supported == qk);
    if (!pv) assert_resident_off(&device.capabilities);
    ++count;
  }
  assert(feof(file) && count != 0u);
  fclose(file);
  printf("SV-to-SDK vectors checked: %u\n", count);
}

int main(int argc, char **argv) {
  assert(argc == 1 || argc == 2);
  check_abi_and_malformed();
  check_dependencies();
  if (argc == 2) check_sv_vectors(argv[1]);
  puts("akv_resident_capability_test: PASS");
  return 0;
}
