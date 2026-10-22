// SPDX-License-Identifier: SHL-0.51
// Reuse the frozen input/oracle without editing the formal test or its body.
#define main gap29_formal_main_unused
#include "../../apps/riscv-tests/isa/rv64uv/vrvv_gap29_fp16_rne_m4.c"
#undef main

static struct {
  unsigned long active, flags, wide_flags;
  uint16_t half[65];
  uint32_t wide[65];
} saved[6];
static volatile uint32_t probe_input[8] __attribute__((aligned(128)));
static unsigned long probe_flags[2];
static uint16_t probe_half[2][8];

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  unsigned long full;
  asm volatile("vsetvli %0, %1, e16, m4, tu, mu"
               : "=r"(full) : "r"(65UL));
  // Keep UART/printf outside the measured instruction sequences.
  for (unsigned pass = 0; pass < 6; ++pass) {
    unsigned long active = pass == 1 ? full - 1 : pass == 4 ? 1 : pass == 5 ? 0 : full;
    for (unsigned i = 0; i < 65; ++i) {
      seed[i] = 0x3555;
      seed_wide[i] = 0x3eaaa000;
      output[i] = 0xdead;
      output_wide[i] = 0xdeadbeef;
    }
    for (unsigned i = 0; i < 9; ++i)
      mask[i] = pass == 3 ? 0 : pass == 2 ? 0x55 : 0xff;
    unsigned long flags, wide_flags;
    asm volatile(
        "vsetvli zero, %[full], e16, m4, tu, mu\n"
        "vle32.v v8, (%[input])\n"
        "vle16.v v16, (%[seed])\n"
        "vle32.v v24, (%[seedw])\n"
        "vlm.v v0, (%[mask])\n"
        "vsetvli zero, %[active], e16, m4, tu, mu\n"
        "csrwi frm, 0\n"
        "csrwi fflags, 0\n"
        "vfncvt.f.f.w v16, v8, v0.t\n"
        "csrr %[flags], fflags\n"
        "csrwi fflags, 0\n"
        "vfwcvt.f.f.v v24, v16, v0.t\n"
        "csrr %[wideflags], fflags\n"
        "vsetvli zero, %[full], e16, m4, tu, mu\n"
        "vse16.v v16, (%[out])\n"
        "vse32.v v24, (%[outw])\n"
        "fence\n"
        : [flags] "=&r"(flags), [wideflags] "=&r"(wide_flags)
        : [full] "r"(full), [active] "r"(active), [input] "r"(input),
          [seed] "r"(seed), [seedw] "r"(seed_wide), [mask] "r"(mask),
          [out] "r"(output), [outw] "r"(output_wide)
        : "memory", "v0", "v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15",
          "v16", "v17", "v18", "v19", "v24", "v25", "v26", "v27", "v28", "v29", "v30", "v31");
    saved[pass].active = active;
    saved[pass].flags = flags;
    saved[pass].wide_flags = wide_flags;
    for (unsigned i = 0; i < 65; ++i) {
      saved[pass].half[i] = output[i];
      saved[pass].wide[i] = output_wide[i];
    }
  }
  // In four Ara lanes, global indices 0 and 4 occupy the two FP32
  // sublanes of Ara lane 0. Both probes have identical VL and all-on mask.
  for (unsigned probe = 0; probe < 2; ++probe) {
    for (unsigned i = 0; i < 8; ++i)
      probe_input[i] = i == probe * 4 ? 0x7f800001 : 0x3f800000;
    mask[0] = 0xff;
    unsigned long flags;
    asm volatile(
        "vsetivli zero, 8, e16, m4, tu, mu\n"
        "vle32.v v8, (%[src])\n"
        "vlm.v v0, (%[mask])\n"
        "csrwi fflags, 0\n"
        "vfncvt.f.f.w v16, v8, v0.t\n"
        "csrr %[flags], fflags\n"
        "vse16.v v16, (%[out])\n"
        "fence\n"
        : [flags] "=&r"(flags)
        : [src] "r"(probe_input), [mask] "r"(mask), [out] "r"(output)
        : "memory", "v0", "v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15",
          "v16", "v17", "v18", "v19");
    probe_flags[probe] = flags;
    for (unsigned i = 0; i < 8; ++i) probe_half[probe][i] = output[i];
  }
  for (unsigned pass = 0; pass < 6; ++pass) {
    unsigned expected_flags = 0, bad = 0;
    for (unsigned i = 0; i < 65; ++i) {
      int selected = i < saved[pass].active && pass != 3 && (pass != 2 || !(i & 1));
      uint16_t eh = i >= full ? 0xdead : selected ? golden[i] : 0x3555;
      uint32_t ew = i >= full ? 0xdeadbeef : selected ? golden_wide[i] : 0x3eaaa000;
      unsigned mismatch = saved[pass].half[i] != eh || saved[pass].wide[i] != ew;
      bad += mismatch;
      if (selected) expected_flags |= golden_flags[i];
      if (mismatch || i == 0 || i == 29 || i == 30 || i == 64)
        printf("D p=%u i=%u sel=%u src=%08x h=%04x/%04x w=%08x/%08x ef=%02x bad=%u\n",
               pass, i, (unsigned)selected, input[i], (unsigned)saved[pass].half[i],
               (unsigned)eh, saved[pass].wide[i], ew,
               selected ? (unsigned)golden_flags[i] : 0, mismatch);
    }
    printf("F p=%u vl=%lu nf=%02lx/%02x wf=%02lx/00 data_bad=%u\n",
           pass, saved[pass].active, saved[pass].flags, expected_flags,
           saved[pass].wide_flags, bad);
    num_failed += bad;
    if (saved[pass].flags != expected_flags || saved[pass].wide_flags != 0) ++num_failed;
  }
  for (unsigned probe = 0; probe < 2; ++probe) {
    unsigned index = probe * 4;
    printf("P sublane=%u i=%u src=7f800001 h=%04x/7e00 nf=%02lx/10\n",
           probe, index, (unsigned)probe_half[probe][index], probe_flags[probe]);
    if (probe_flags[probe] != 0x10 || probe_half[probe][index] != 0x7e00) ++num_failed;
  }
  asm volatile("csrwi frm, 0" ::: "memory");
  EXIT_CHECK();
}
