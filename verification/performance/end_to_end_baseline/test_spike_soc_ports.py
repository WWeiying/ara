#!/usr/bin/env python3
"""Native callback tests against the actual local Spike API; never runs Spike."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart')
SOURCE = HERE/'spike_soc_ports.cc'

HARNESS = r'''
#define SPIKE_SOC_PORTS_UNIT_TEST
#include "spike_soc_ports.cc"
#include <cassert>
#include <cstring>
#include <memory>

static void callbacks() {
  spike_soc_ports_t device;
  assert(device.size() == UINT64_C(0x10000020));
  assert(device.uart_bytes() == 0 && !device.exit_seen());
  uint8_t bytes[16];
  std::memset(bytes, 0xa5, sizeof(bytes));
  assert(device.load(device.dram_end_offset, 8, bytes));
  const uint8_t end[8] = {0, 0, 0, 0xc0, 0, 0, 0, 0};
  assert(std::memcmp(bytes, end, 8) == 0 && bytes[8] == 0xa5);
  assert(device.load(device.dram_base_offset, 8, bytes));
  const uint8_t start[8] = {0, 0, 0, 0x80, 0, 0, 0, 0};
  assert(std::memcmp(bytes, start, 8) == 0 && bytes[8] == 0xa5);
  const reg_t addresses[] = {0, 1, device.eoc_offset, device.eoc_offset+1,
      device.dram_base_offset, device.dram_base_offset+1,
      device.dram_end_offset, device.dram_end_offset+1,
      device.span-1, device.span, UINT64_MAX};
  const size_t lengths[] = {0, 1, 2, 4, 8, 16};
  for (reg_t addr : addresses) for (size_t len : lengths) {
    if (!(len == 8 && (addr == device.dram_base_offset || addr == device.dram_end_offset))) {
      std::memset(bytes, 0xa5, sizeof(bytes));
      assert(!device.load(addr, len, bytes));
      for (uint8_t value : bytes) assert(value == 0xa5);
    }
    if (!((addr == 0 && len == 1) || (addr == device.eoc_offset && len == 8)))
      assert(!device.store(addr, len, bytes));
  }
  assert(!device.load(device.dram_end_offset, 8, nullptr));
  assert(!device.store(0, 1, nullptr));
  assert(!device.store(device.eoc_offset, 8, nullptr));
  assert(device.uart_bytes() == 0 && !device.exit_seen());
  std::puts("SPIKE_SOC_PORTS_CALLBACK_UNIT_PASS");
}

struct exit_event_t { unsigned calls = 0; uint64_t status = 0; int encoded = 0; };
static void exit_callback(void* context, uint64_t status) {
  auto* event = static_cast<exit_event_t*>(context);
  ++event->calls;
  event->status = status;
  event->encoded = spike_soc_ports_htif_status(status);
}

static void eoc(bool success) {
  spike_soc_ports_t device;
  exit_event_t event;
  device.set_exit_callback(exit_callback, &event);
  const uint8_t uart[] = {'A', 0, 255, '\n'};
  for (uint8_t byte : uart) assert(device.store(0, 1, &byte));
  assert(device.uart_bytes() == 4);
  const uint64_t status = success ? 0 : UINT64_C(0x8000000000000100);
  uint8_t bytes[8];
  for (size_t i=0; i<8; ++i) bytes[i] = uint8_t(status >> (8*i));
  assert(device.store(device.eoc_offset, 8, bytes));
  assert(device.exit_seen() && device.exit_status() == status);
  assert(event.calls == 1 && event.status == status);
  assert(event.encoded == (success ? 1 : 3));
  assert((event.encoded >> 1) == (success ? 0 : 1));
  // Guest EOC loops must not overwrite the first result or print more markers.
  std::memset(bytes, success ? 0xff : 0, sizeof(bytes));
  assert(device.store(device.eoc_offset, 8, bytes));
  assert(device.store(device.eoc_offset, 8, bytes));
  assert(event.calls == 1 && event.status == status && device.exit_status() == status);
  assert(spike_soc_ports_htif_status(UINT64_C(0x8000000000000000)) == 3);
  assert(spike_soc_ports_htif_status(UINT64_MAX) == 3);
}

static void factory() {
  reg_t base = 0;
  std::unique_ptr<spike_soc_ports_t> device(spike_soc_ports_parse_from_fdt(nullptr, nullptr, &base, {}));
  assert(base == UINT64_C(0xc0000000) && device->size() == UINT64_C(0x10000020));
  const std::string dts = spike_soc_ports_generate_dts(nullptr, {});
  assert(dts.find("spike-soc-ports@c0000000 {") != std::string::npos);
  assert(dts.find("compatible = \"ara,spike-soc-ports\";") != std::string::npos);
  assert(dts.find("reg = <0x0 0xc0000000 0x0 0x10000020>;") != std::string::npos);
  assert(dts.find("};\n") != std::string::npos);
  bool parse_rejected = false, dts_rejected = false, null_rejected = false;
  try { spike_soc_ports_parse_from_fdt(nullptr, nullptr, &base, {"unexpected"}); }
  catch (const std::invalid_argument&) { parse_rejected = true; }
  try { spike_soc_ports_generate_dts(nullptr, {"unexpected"}); }
  catch (const std::invalid_argument&) { dts_rejected = true; }
  try { spike_soc_ports_parse_from_fdt(nullptr, nullptr, nullptr, {}); }
  catch (const std::invalid_argument&) { null_rejected = true; }
  assert(parse_rejected && dts_rejected && null_rejected);
  std::puts("SPIKE_SOC_PORTS_FACTORY_UNIT_PASS");
}

int main(int argc, char** argv) {
  assert(argc == 2);
  if (!std::strcmp(argv[1], "callbacks")) callbacks();
  else if (!std::strcmp(argv[1], "factory")) factory();
  else if (!std::strcmp(argv[1], "eoc-zero")) eoc(true);
  else if (!std::strcmp(argv[1], "eoc-nonzero")) eoc(false);
  else return 2;
  return 0;
}
'''


class SpikeSocPortsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='spike-soc-ports-unit-')
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        harness = root/'callbacks.cc'; harness.write_text(HARNESS)
        cls.image = root/'callbacks'
        compiler = shutil.which('g++')
        if compiler is None:
            raise RuntimeError('Native g++ required')
        command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O2',
                   '-I'+str(SPIKE/'riscv'), '-I'+str(HERE), str(harness), '-o', str(cls.image)]
        result = subprocess.run(command, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))

    def run_callback(self, mode):
        result = subprocess.run([str(self.image), mode], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertEqual(result.stderr, b'')
        return result.stdout

    def test_exact_loads_and_unknown_io_no_side_effects(self):
        self.assertEqual(self.run_callback('callbacks'), b'SPIKE_SOC_PORTS_CALLBACK_UNIT_PASS\n')

    def test_uart_binary_bytes_and_zero_status_event(self):
        self.assertEqual(self.run_callback('eoc-zero'), b'A\x00\xff\nSPIKE_SOC_EXIT status=0 uart_bytes=4\n')

    def test_nonzero_64bit_little_endian_status_event(self):
        self.assertEqual(self.run_callback('eoc-nonzero'),
                         b'A\x00\xff\nSPIKE_SOC_EXIT status=9223372036854776064 uart_bytes=4\n')

    def test_noargs_factory_and_fixed_dts(self):
        self.assertEqual(self.run_callback('factory'), b'SPIKE_SOC_PORTS_FACTORY_UNIT_PASS\n')

    def test_registration_and_production_htif_callback_remain_present(self):
        source = SOURCE.read_text()
        self.assertIn('REGISTER_DEVICE(spike_soc_ports, spike_soc_ports_parse_from_fdt, spike_soc_ports_generate_dts)', source)
        self.assertIn('->htif_exit(spike_soc_ports_htif_status(status));', source)
        self.assertNotIn('std::exit', source)
        self.assertIn('#ifndef SPIKE_SOC_PORTS_UNIT_TEST\nREGISTER_DEVICE', source)


if __name__ == '__main__':
    unittest.main()
