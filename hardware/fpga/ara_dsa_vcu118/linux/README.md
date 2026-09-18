# Linux bring-up

This is the first Linux handoff for the existing passive UART boot path. It
uses the current VCU118 bitstream and places OpenSBI, the kernel, the device
tree, and a small initramfs in DDR before executing OpenSBI. The DTB is also
embedded in OpenSBI so its platform initialization does not depend on the
initial register contents supplied by the passive UART `EXEC` call.

## Build

The build host needs the RISC-V Buildroot SDK used for the kernel and OpenSBI,
plus `dtc` and `cpio`:

```bash
cd hardware/fpga/ara_dsa_vcu118
bash linux/build_linux_bringup.sh
```

Override `SDK`, `KERNEL_IMAGE`, `OPENSBI_SRC`, or `OUT` when the SDK is stored
elsewhere. The script emits:

| File | DDR address |
| --- | ---: |
| `fw_jump.elf` | `0x80000000` |
| `ara_vcu118.dtb` | `0x80100000` |
| `Image` | `0x80200000` |
| `initramfs.cpio` | `0x88000000` |

The repository also includes the resulting first-boot payloads in
`linux/artifacts/`. This is the directory to use on a Windows board PC that
does not have the RISC-V toolchain.

## Windows load

After programming the existing `.bit` and `.ltx` in Vivado, run from the
repository root on the board PC:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/uart_load.py `
  --port COM6 `
  --elf hardware/fpga/ara_dsa_vcu118/linux/artifacts/fw_jump.elf `
  --load 0x80200000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image `
  --load 0x80100000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/ara_vcu118.dtb `
  --load 0x88000000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio `
  --no-readback --chunk-size 4096 --seconds 120
```

At 115200 baud, transferring the kernel takes a long time even with readback
disabled. Expected output includes an OpenSBI banner, Linux early console
messages through the SBI debug console, followed by the normal UART console,
and:

```text
Ara DSA VCU118 Linux init reached
Linux console, DDR and RVV handoff are alive
```

This validates the OS handoff only. It is not yet a persistent Linux boot or a
llama.cpp deployment: the current image has no shell, network, storage driver,
or model filesystem. A real llama.cpp run still needs a storage path or a
higher-bandwidth host loader and a rootfs with the application and GGUF model.
