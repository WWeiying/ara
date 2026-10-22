#include <stddef.h>
#include <stdint.h>
#include "../qbs/qbs_ref.h"
#include "qbs_fma_align795_data.h"

#ifdef QF_HOST
#include <stdio.h>
#include <string.h>
static unsigned current_phase;
static void trace(const qbs_trace_event_t *event, void *opaque) {
  (void)opaque;
  if (event->kind == QBS_TRACE_BLOCK) {
    union { float f; uint32_t u; } before = {event->accumulator_before};
    union { float f; uint32_t u; } after = {event->accumulator_after};
    printf("B %u %u %u %d %d %08x %08x\n", current_phase,
           event->output, event->k_block, event->block_dot,
           event->block_aux, before.u, after.u);
  }
}
int main(void) {
  for (current_phase = 0; current_phase < 2; ++current_phase) {
    qbs_descriptor_t descriptor = {QF_HEADER, (uintptr_t)qf_inputs[current_phase].weights};
    float destination[32];
    qbs_ref_result_t result;
    memset(destination, 0x7a, sizeof(destination));
    qbs_ref_status_t status = qbs_ref_execute(&descriptor, 1, 8, 1024,
        (uintptr_t)qf_inputs[current_phase].activation,
        qf_inputs[current_phase].weights, 576,
        qf_inputs[current_phase].activation, 584,
        destination, 32, trace, NULL, &result);
    if (status != QBS_REF_OK) return 1;
    printf("F %u %u %u\n", current_phase, result.fflags, result.active_outputs);
    for (unsigned i = 0; i < 32; ++i) {
      union { float f; uint32_t u; } value = {destination[i]};
      printf("Q %u %u %08x\n", current_phase, i, value.u);
    }
  }
  return 0;
}
#else
volatile uint32_t qf_result[2], num_failed;
volatile struct qf_snapshot {
  uint32_t before[4], words[1024], after[4];
} qf_snap[2][2] __attribute__((aligned(128)));
volatile uint64_t qf_csr[2][6];
static qbs_descriptor_t qf_descriptor __attribute__((aligned(16)));
#ifdef QF_SOFTWARE_REFERENCE
static uint32_t qf_reference_result[32] __attribute__((aligned(128)));
#endif

static void check(uint64_t actual, uint64_t expected) {
  ++qf_result[0];
  if (actual != expected) ++num_failed;
}

__attribute__((noinline))
static void snapshot(volatile uint32_t *destination) {
  asm volatile(".option push\n.option arch,+v\nmv t0,%0\n"
    ".irp R,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31\n"
    "vs1r.v v\\R,(t0)\naddi t0,t0,128\n.endr\n.option pop\nfence rw,rw\n"
    : : "r"(destination) : "t0", "memory");
}

#ifdef QF_SOFTWARE_REFERENCE
static uint32_t half_normal(uint16_t word) {
  return word == 0 ? 0 : ((uint32_t)(word >> 10) + 112) << 23 |
                          (uint32_t)(word & 1023) << 13;
}

__attribute__((noinline))
static uint32_t update(uint16_t weight, uint32_t activation, int32_t dot,
                       uint32_t accumulator) {
  uint32_t result;
  asm volatile("fmv.w.x ft0,%1\nfmv.w.x ft1,%2\n"
    ".global qf_scale_mul\nqf_scale_mul: fmul.s ft0,ft0,ft1,rne\nfcvt.s.w ft2,%3,rne\nfmv.w.x ft3,%4\n"
    ".global qf_dot_fma\nqf_dot_fma: fmadd.s ft0,ft0,ft2,ft3,rne\n"
    "fmv.w.x ft3,zero\n.global qf_min_mul\nqf_min_mul: fmul.s ft3,ft3,ft1,rne\n"
    "fsgnjn.s ft3,ft3,ft3\nfcvt.s.w ft4,zero,rne\n"
    ".global qf_min_fma\nqf_min_fma: fmadd.s ft0,ft3,ft4,ft0,rne\nfmv.x.w %0,ft0\n"
    : "=&r"(result) : "r"(half_normal(weight)), "r"(activation),
      "r"(dot), "r"(accumulator) : "ft0", "ft1", "ft2", "ft3", "ft4", "memory");
  return result;
}

__attribute__((noinline))
static void software_reference(unsigned phase) {
  for (unsigned i = 0; i < 32; ++i) qf_reference_result[i] = 0;
  for (unsigned row = 0; row < 2; ++row) {
    uint32_t accumulator = 0;
    for (unsigned block = 0; block < 2; ++block) {
      const qbs_block_q4_k_t *w = &qf_inputs[phase].weights[2 * row + block];
      const qbs_block_q8_k_t *a = &qf_inputs[phase].activation[block];
      int32_t dot = 0;
      for (unsigned i = 0; i < 256; ++i) {
        unsigned group = i / 32;
        unsigned scale = group < 4 ? w->scales[group] & 63 :
          (w->scales[group + 4] & 15) | ((w->scales[group - 4] >> 6) << 4);
        unsigned quant = (w->qs[(i / 64) * 32 + i % 32] >> ((i % 64 >= 32) ? 4 : 0)) & 15;
        dot += (int32_t)(scale * quant) * a->qs[i];
      }
      union { float f; uint32_t u; } activation = {a->d};
      accumulator = update(w->d, activation.u, dot, accumulator);
    }
    qf_reference_result[row] = accumulator;
  }
  asm volatile(".option push\n.option arch,+v\n"
    ".global qf_reference_load\nqf_reference_load: vle32.v v8,(%0)\n.option pop\n"
    : : "r"(qf_reference_result) : "memory");
}
#else
__attribute__((noinline))
static void native_command(const qbs_block_q8_k_t *activation) {
  register uintptr_t a0 asm("a0") = (uintptr_t)&qf_descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  asm volatile(".global qf_native_site\nqf_native_site: .word 0x00b5045b\n"
               : "+r"(a0), "+r"(a1) : : "memory");
}
#endif

int main(void) {
  uint64_t vlenb;
  asm volatile("csrr %0,vlenb" : "=r"(vlenb));
  check(vlenb, 128);
  for (unsigned phase = 0; phase < 2; ++phase) {
    for (unsigned side = 0; side < 2; ++side)
      for (unsigned i = 0; i < 4; ++i)
        qf_snap[phase][side].before[i] = qf_snap[phase][side].after[i] = QF_GUARD;
    qf_descriptor.header = QF_HEADER;
    qf_descriptor.weight_base = (uintptr_t)qf_inputs[phase].weights;
    check(qf_descriptor.header, QF_HEADER);
    check(qf_descriptor.weight_base & 1, 0);
    asm volatile(".option push\n.option arch,+v\n"
      "csrw vstart,zero\ncsrw vcsr,zero\ncsrw fcsr,zero\n"
      "li t0,32\nvsetvli zero,t0,e32,m1,tu,mu\n"
      ".irp R,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31\n"
      "li t0,0x6a000000+\\R\nvmv.v.x v\\R,t0\n.endr\n.option pop\n"
      : : : "t0", "memory");
    snapshot(qf_snap[phase][0].words);
#ifdef QF_SOFTWARE_REFERENCE
    software_reference(phase);
#else
    native_command(qf_inputs[phase].activation);
#endif
    uint64_t vl, vtype, start, vcsr, fcsr, flags;
    asm volatile("csrr %0,vl\ncsrr %1,vtype\ncsrr %2,vstart\n"
      "csrr %3,vcsr\ncsrr %4,fcsr\ncsrr %5,fflags\n"
      : "=r"(vl), "=r"(vtype), "=r"(start), "=r"(vcsr), "=r"(fcsr), "=r"(flags));
    uint64_t values[6] = {vl, vtype, start, vcsr, fcsr, flags};
    for (unsigned i = 0; i < 6; ++i) {
      qf_csr[phase][i] = values[i];
      check(values[i], qf_csr_gold[i]);
    }
    snapshot(qf_snap[phase][1].words);
    for (unsigned side = 0; side < 2; ++side) {
      for (unsigned i = 0; i < 1024; ++i) {
        unsigned reg = i / 32, element = i % 32;
        uint32_t expected = side == 1 && reg == 8 ?
          (element < 2 ? qf_output_gold[element] : 0) : 0x6a000000u + reg;
        check(qf_snap[phase][side].words[i], expected);
      }
      for (unsigned i = 0; i < 4; ++i) {
        check(qf_snap[phase][side].before[i], QF_GUARD);
        check(qf_snap[phase][side].after[i], QF_GUARD);
      }
    }
    const unsigned char *bytes = (const unsigned char *)&qf_inputs[phase];
    for (unsigned i = 0; i < 1280; ++i) check(bytes[i], qf_input_gold[phase][i]);
  }
  qf_result[1] = num_failed;
  return num_failed != 0 || qf_result[0] != QF_CHECKS;
}
#endif
