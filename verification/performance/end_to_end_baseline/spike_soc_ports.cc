// MMIO plumbing only. No computation, instruction decoding, or ISA emulation.
#include "abstract_device.h"
#ifndef SPIKE_SOC_PORTS_UNIT_TEST
#include "sim.h"
#endif

#include <cinttypes>
#include <cstdio>
#include <stdexcept>

class spike_soc_ports_t final : public abstract_device_t {
 public:
  static constexpr reg_t base_address = UINT64_C(0xc0000000);
  static constexpr reg_t span = UINT64_C(0x10000020);
  static constexpr reg_t eoc_offset = UINT64_C(0x10000000);
  static constexpr reg_t dram_base_offset = UINT64_C(0x10000008);
  static constexpr reg_t dram_end_offset = UINT64_C(0x10000010);

  spike_soc_ports_t() = default;

  using exit_callback_t = void (*)(void*, uint64_t);
  void set_exit_callback(exit_callback_t callback, void* context) {
    exit_callback_ = callback;
    exit_context_ = context;
  }

  reg_t size() override { return span; }

  bool load(reg_t addr, size_t len, uint8_t* bytes) override {
    if (bytes == nullptr || len != 8) return false;
    uint64_t value;
    if (addr == dram_end_offset) value = UINT64_C(0xc0000000);
    else if (addr == dram_base_offset) value = UINT64_C(0x80000000);
    else return false;
    for (size_t i = 0; i < 8; ++i) bytes[i] = static_cast<uint8_t>(value >> (8*i));
    return true;
  }

  bool store(reg_t addr, size_t len, const uint8_t* bytes) override {
    if (bytes == nullptr) return false;
    if (addr == 0 && len == 1) {
      if (std::fputc(bytes[0], stdout) == EOF) return false;
      ++uart_bytes_;
      std::fflush(stdout);
      return true;
    }
    if (addr != eoc_offset || len != 8) return false;
    if (exit_seen_) return true;
    if (exit_callback_ == nullptr) return false;
    uint64_t status = 0;
    for (size_t i = 0; i < 8; ++i) status |= uint64_t(bytes[i]) << (8*i);
    exit_seen_ = true;
    exit_status_ = status;
    std::fprintf(stdout, "SPIKE_SOC_EXIT status=%" PRIu64 " uart_bytes=%" PRIu64 "\n", status, uart_bytes_);
    std::fflush(stdout);
    exit_callback_(exit_context_, status);
    return true;
  }

  uint64_t uart_bytes() const { return uart_bytes_; }
  bool exit_seen() const { return exit_seen_; }
  uint64_t exit_status() const { return exit_status_; }

 private:
  uint64_t uart_bytes_ = 0;
  bool exit_seen_ = false;
  uint64_t exit_status_ = 0;
  exit_callback_t exit_callback_ = nullptr;
  void* exit_context_ = nullptr;
};

static int spike_soc_ports_htif_status(uint64_t status) {
  // HTIF takes int and shifts right by one; retain failure even for high bits.
  return ((status != 0 ? 1 : 0) << 1) | 1;
}

#ifndef SPIKE_SOC_PORTS_UNIT_TEST
static void spike_soc_ports_htif_exit(void* context, uint64_t status) {
  static_cast<sim_t*>(context)->htif_exit(spike_soc_ports_htif_status(status));
}
#endif

static void spike_soc_ports_no_args(const std::vector<std::string>& args) {
  if (!args.empty()) throw std::invalid_argument("spike_soc_ports takes no arguments");
}

spike_soc_ports_t* spike_soc_ports_parse_from_fdt(
    const void*, const sim_t* sim, reg_t* base, const std::vector<std::string>& args) {
  spike_soc_ports_no_args(args);
  if (base == nullptr) throw std::invalid_argument("spike_soc_ports requires a base output");
#ifndef SPIKE_SOC_PORTS_UNIT_TEST
  if (sim == nullptr) throw std::invalid_argument("spike_soc_ports requires a simulator");
#else
  (void)sim;
#endif
  auto* device = new spike_soc_ports_t();
#ifndef SPIKE_SOC_PORTS_UNIT_TEST
  device->set_exit_callback(spike_soc_ports_htif_exit, const_cast<sim_t*>(sim));
#endif
  *base = spike_soc_ports_t::base_address;
  return device;
}

std::string spike_soc_ports_generate_dts(const sim_t*, const std::vector<std::string>& args) {
  spike_soc_ports_no_args(args);
  return "    spike-soc-ports@c0000000 {\n"
         "      compatible = \"ara,spike-soc-ports\";\n"
         "      reg = <0x0 0xc0000000 0x0 0x10000020>;\n"
         "      status = \"okay\";\n"
         "    };\n";
}

#ifndef SPIKE_SOC_PORTS_UNIT_TEST
REGISTER_DEVICE(spike_soc_ports, spike_soc_ports_parse_from_fdt, spike_soc_ports_generate_dts)
#endif
