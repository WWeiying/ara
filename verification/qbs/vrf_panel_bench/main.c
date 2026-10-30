#include <stdint.h>
#include "printf.h"
#include "vrf_panel.h"
#include "panel_data.h"

static qbs_descriptor_t descriptors[PANEL_STRIPES][2];
static qbs_vrf_panel_record_t records[PANEL_STRIPES];
static float output[16 + PANEL_M*PANEL_N + 16] __attribute__((aligned(64)));

static uint64_t cycle(void) {
  uint64_t value;
  asm volatile("fence rw, rw; rdcycle %0":"=r"(value)::"memory");
  return value;
}

static uint32_t load_u32(const unsigned char *bytes) {
  return (uint32_t)bytes[0] | ((uint32_t)bytes[1]<<8) |
         ((uint32_t)bytes[2]<<16) | ((uint32_t)bytes[3]<<24);
}

__attribute__((noinline)) static qbs_vrf_panel_status_t execute(unsigned striped) {
  const unsigned count=striped ? PANEL_STRIPES:1;
  for (unsigned s=0;s<count;s++) {
    for (unsigned tile=0;tile<2;tile++) {
      qbs_descriptor_fields_t fields={
        .descriptor_version=QBS_DESCRIPTOR_VERSION,
        .weight_profile=QBS_WEIGHT_PROFILE_Q6_K,
        .activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
        .weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        .activation_layout=QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
        .n=32,.k_blocks=striped ? panel_stripes[s].k_blocks:PANEL_K_BLOCKS,
        .activation_access=striped ? (tile==0 ? QBS_ACTIVATION_ACCESS_FILL:
            (s+1==count ? QBS_ACTIVATION_ACCESS_RELEASE:QBS_ACTIVATION_ACCESS_REUSE)):
            QBS_ACTIVATION_ACCESS_DIRECT,
        .context_id=0,.context_generation=striped ? s+1:0
      };
      descriptors[s][tile].header=qbs_pack_descriptor_header(&fields);
      descriptors[s][tile].weight_base=(uintptr_t)(striped ?
          panel_weight_striped_r4+panel_stripes[s].weight_offset[tile]:
          panel_weight_full_r4+panel_full_weight_offset[tile]);
    }
    records[s]=(qbs_vrf_panel_record_t){&descriptors[s][0],&descriptors[s][1],
        panel_activation_q8k_m4+(striped ? panel_stripes[s].activation_offset:0)};
  }
  if (striped)
    return qbs_vrf_panel_run(records,count,output+16,output+48,PANEL_N,32,32);
  return qbs_vrf_panel_direct_run(records,output+16,output+48,PANEL_N,32,32);
}

int main(void) {
  static const unsigned modes[4]={0,1,1,0};
  uint64_t timings[4],checksums[4];
  unsigned flags[4],errors=0;
  for (unsigned trial=0;trial<4;trial++) {
    unsigned char *bytes=(unsigned char *)output;
    for (unsigned j=0;j<sizeof(output);j++) bytes[j]=0xa5;
    asm volatile("csrwi fcsr, 0; csrwi vcsr, 5":::"memory");
    const uint64_t begin=cycle();
    const qbs_vrf_panel_status_t status=execute(modes[trial]);
    timings[trial]=cycle()-begin;
    unsigned vcsr;
    asm volatile("frcsr %0; csrr %1, vcsr":"=r"(flags[trial]),"=r"(vcsr)::"memory");
    errors+=status!=QBS_VRF_PANEL_OK || flags[trial]!=PANEL_EXPECTED_FFLAGS || vcsr!=5;
    uint64_t hash=UINT64_C(14695981039346656037);
    for (unsigned i=0;i<PANEL_M*PANEL_N;i++) {
      const unsigned char *actual=bytes+(16+i)*4;
      errors+=load_u32(actual)!=load_u32(panel_expected_f32+i*4);
      for (unsigned b=0;b<4;b++) hash=(hash^actual[b])*UINT64_C(1099511628211);
    }
    for (unsigned i=0;i<16*4;i++)
      errors+=bytes[i]!=0xa5 || bytes[(16+PANEL_M*PANEL_N)*4+i]!=0xa5;
    checksums[trial]=hash;
    if (trial) errors+=hash!=checksums[0] || flags[trial]!=flags[0];
  }
  for (unsigned t=0;t<4;t++)
    printf("VRF_PANEL_TRIAL trial=%u path=%s cycles=%lu flags=%u checksum=%016lx\n",
           t,modes[t] ? "striped":"direct",(unsigned long)timings[t],flags[t],
           (unsigned long)checksums[t]);
  printf("VRF_PANEL_RESULT errors=%u m=4 n=64 k=8960 outputs=256 calls=4 commands=40 preparation_timed=0 descriptor_setup_timed=1\n",errors);
  return errors ? 1:0;
}
