#include "vrf_panel.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "FAIL line=%d: %s\n", __LINE__, #x); exit(1); \
} } while (0)

static qbs_descriptor_t descriptors[256][2];
static qbs_vrf_panel_record_t records[256];
static _Alignas(16) unsigned char activation[4672];
static _Alignas(16) float outputs[4 * 80];
static size_t mock_vlenb = 128;
static int bad_cap = -1;
static unsigned issues, info_reads, vlen_reads, cases;
static size_t expected_count, expected_n0, expected_n1;

size_t qbs_vrf_panel_vlenb(void) { ++vlen_reads; return mock_vlenb; }
uint64_t qbs_vrf_panel_info(unsigned index) {
  ++info_reads;
  CHECK(index <= 4);
  uint64_t value = index == 4 ? 1 : qbs_capability_word(index, 1024);
  return value ^ (index == (unsigned)bad_cap ? 1 : 0);
}
void qbs_vrf_panel_asm(const qbs_vrf_panel_record_t *r, size_t count,
                       float *o0, float *o1, size_t stride, size_t n0, size_t n1) {
  ++issues;
  CHECK(r == records && count == expected_count && stride == 80);
  CHECK(o0 == outputs && o1 == outputs + 32);
  CHECK(n0 == expected_n0 && n1 == expected_n1);
}

static void prepare(size_t count, size_t n0, size_t n1, unsigned profile) {
  expected_count = count; expected_n0 = n0; expected_n1 = n1;
  issues = info_reads = vlen_reads = 0;
  mock_vlenb = 128; bad_cap = -1;
  for (size_t i = 0; i < count; ++i) {
    qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = profile,
      .activation_profile = qbs_default_activation_profile(profile),
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
      .k_blocks = profile == QBS_WEIGHT_PROFILE_Q6_K ? (i + 1 == count ? 3 : 4) : 32,
      .context_id = 0, .context_generation = (uint8_t)i
    };
    fields.n = (uint8_t)n0;
    fields.activation_access = QBS_ACTIVATION_ACCESS_FILL;
    descriptors[i][0].header = qbs_pack_descriptor_header(&fields);
    descriptors[i][0].weight_base = 0x10000 + i * 0x10000;
    fields.n = (uint8_t)n1;
    fields.activation_access = i + 1 == count ? QBS_ACTIVATION_ACCESS_RELEASE :
                                               QBS_ACTIVATION_ACCESS_REUSE;
    descriptors[i][1].header = qbs_pack_descriptor_header(&fields);
    descriptors[i][1].weight_base = descriptors[i][0].weight_base + 0x8000;
    records[i] = (qbs_vrf_panel_record_t){&descriptors[i][0], &descriptors[i][1], activation};
  }
}

static void expect(qbs_vrf_panel_status_t status) {
  CHECK(qbs_vrf_panel_run(records, expected_count, outputs, outputs + 32, 80,
                         expected_n0, expected_n1) == status);
  CHECK(issues == (status == QBS_VRF_PANEL_OK ? 1u : 0u));
  if (status == QBS_VRF_PANEL_BAD_ARGUMENT || status == QBS_VRF_PANEL_BAD_DESCRIPTOR)
    CHECK(info_reads == 0 && vlen_reads == 0);
  if (status == QBS_VRF_PANEL_OK) CHECK(info_reads == 5 && vlen_reads == 1);
  ++cases;
}

int main(void) {
  CHECK(qbs_encode_qbexec(8, 10, 11, 4) == UINT32_C(0x06b5045b));
  CHECK(qbs_encode_qbexec(16, 10, 11, 4) == UINT32_C(0x06b5085b));
  CHECK(qbs_encode_qbacc(8, 10, 11, 4) == UINT32_C(0x16b5045b));
  CHECK(qbs_encode_qbacc(16, 10, 11, 4) == UINT32_C(0x16b5085b));
  CHECK(qbs_encode_qbinfo(10, 10) == UINT32_C(0x0005155b));
  for (size_t count = 1; count <= 256; ++count) {
    prepare(count, 32, 5, QBS_WEIGHT_PROFILE_Q6_K); expect(QBS_VRF_PANEL_OK);
    prepare(count, 1, 32, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT); expect(QBS_VRF_PANEL_OK);
  }
  for (size_t n0 = 1; n0 <= 32; ++n0)
    for (size_t n1 = 1; n1 <= 32; ++n1) {
      prepare(2, n0, n1, QBS_WEIGHT_PROFILE_Q6_K); expect(QBS_VRF_PANEL_OK);
    }

  for (unsigned mutation = 0; mutation < 15; ++mutation) {
    prepare(9, 32, 5, QBS_WEIGHT_PROFILE_Q6_K);
    qbs_descriptor_fields_t f = qbs_unpack_descriptor_header(descriptors[8][1].header);
    switch (mutation) {
      case 0: f.activation_access = QBS_ACTIVATION_ACCESS_REUSE; break;
      case 1: f.context_generation ^= 1; break;
      case 2: f.context_id = 1; break;
      case 3: f.n = 6; break;
      case 4: f.k_blocks = 4; break;
      case 5: f.weight_profile = QBS_WEIGHT_PROFILE_Q4_K; break;
      case 6: f.activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR; break;
      case 7: f.descriptor_version = 1; break;
      case 8: f.weight_layout = 0; break;
      case 9: f.activation_profile = QBS_ACTIVATION_PROFILE_Q8_0; break;
      default: break;
    }
    descriptors[8][1].header = qbs_pack_descriptor_header(&f);
    if (mutation == 10) descriptors[8][1].header |= UINT64_C(1) << 63;
    if (mutation == 11) descriptors[8][1].weight_base |= 1;
    if (mutation == 12) descriptors[8][1].weight_base = 0;
    if (mutation == 13) descriptors[8][1].weight_base = descriptors[8][0].weight_base;
    if (mutation == 14) {
      f = qbs_unpack_descriptor_header(descriptors[8][0].header);
      f.k_blocks = 5; f.n = 32; f.activation_access = QBS_ACTIVATION_ACCESS_FILL;
      descriptors[8][0].header = qbs_pack_descriptor_header(&f);
      f.n = 5; f.activation_access = QBS_ACTIVATION_ACCESS_RELEASE;
      descriptors[8][1].header = qbs_pack_descriptor_header(&f);
    }
    expect(QBS_VRF_PANEL_BAD_DESCRIPTOR);
  }
  prepare(1, 32, 5, QBS_WEIGHT_PROFILE_Q6_K);
  records[0].tile0 = (const qbs_descriptor_t *)((uintptr_t)&descriptors[0][0] + 1);
  expect(QBS_VRF_PANEL_BAD_ARGUMENT);
  prepare(1, 32, 5, QBS_WEIGHT_PROFILE_Q6_K);
  records[0].activation = NULL; expect(QBS_VRF_PANEL_BAD_ARGUMENT);
  prepare(1, 32, 5, QBS_WEIGHT_PROFILE_Q6_K);
  records[0].activation = (void *)(UINTPTR_MAX - 3); expect(QBS_VRF_PANEL_BAD_ARGUMENT);

  prepare(1, 32, 5, QBS_WEIGHT_PROFILE_Q6_K);
#define BAD(r, c, o0, o1, s, n0, n1) do { \
  CHECK(qbs_vrf_panel_run(r, c, o0, o1, s, n0, n1) == QBS_VRF_PANEL_BAD_ARGUMENT); \
  CHECK(issues == 0 && info_reads == 0 && vlen_reads == 0); ++cases; \
} while (0)
  BAD(NULL, 1, outputs, outputs + 32, 80, 32, 5);
  BAD(records, 0, outputs, outputs + 32, 80, 32, 5);
  BAD(records, 257, outputs, outputs + 32, 80, 32, 5);
  BAD(records, SIZE_MAX, outputs, outputs + 32, 80, 32, 5);
  BAD(records, 1, NULL, outputs + 32, 80, 32, 5);
  BAD(records, 1, outputs, outputs, 80, 32, 5);
  BAD(records, 1, outputs, outputs + 80, 80, 32, 5);
  BAD(records, 1, outputs, outputs + 32, 31, 32, 5);
  BAD(records, 1, outputs, outputs + 32, SIZE_MAX, 32, 5);
  BAD(records, 1, outputs, outputs + 32, 80, 0, 5);
  BAD(records, 1, outputs, outputs + 32, 80, 33, 5);
  BAD(records, 1, outputs, outputs + 32, 80, 32, SIZE_MAX);
  BAD(records, 1, (float *)(UINTPTR_MAX - 3), outputs + 32, 80, 32, 5);
  for (int cap = 0; cap <= 4; ++cap) {
    prepare(2, 32, 5, QBS_WEIGHT_PROFILE_Q6_K);
    bad_cap = cap; expect(QBS_VRF_PANEL_UNSUPPORTED);
  }
  prepare(2, 32, 5, QBS_WEIGHT_PROFILE_Q6_K);
  mock_vlenb = 64; expect(QBS_VRF_PANEL_UNSUPPORTED);
  CHECK(info_reads == 0);
  printf("QBS_VRF_PANEL_PREFLIGHT_PASS cases=%u\n", cases);
  return 0;
}
