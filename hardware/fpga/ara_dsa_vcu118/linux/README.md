# Linux bring-up

This is the Linux handoff for the existing passive UART boot path. It uses the
current VCU118 bitstream and places OpenSBI, the kernel, the device tree, and
an interactive BusyBox initramfs in DDR before executing OpenSBI. The DTB is
also embedded in OpenSBI so its platform initialization does not depend on the
initial register contents supplied by the passive UART `EXEC` call.

## Build

The build host needs the RISC-V Buildroot SDK used for the kernel, OpenSBI,
and BusyBox, plus `dtc` and `cpio`:

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

For the regenerated fast-boot bitstream, use the CP2105 Enhanced COM port for
the payload and switch the host back to the Linux console rate after `EXEC`:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/uart_load.py `
  --port COM7 --baud 1562500 --console-baud 115200 `
  --elf hardware/fpga/ara_dsa_vcu118/linux/artifacts/fw_jump.elf `
  --load 0x80200000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image `
  --load 0x80100000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/ara_vcu118.dtb `
  --load 0x88000000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio `
  --no-readback --chunk-size 65536 --seconds 120
```

At 115200 baud, transferring the kernel takes a long time even with readback
disabled. Expected output includes an OpenSBI banner, Linux early console
messages through the SBI debug console, followed by the normal UART console,
and:

```text
Ara DSA VCU118 Linux init reached
Linux console, DDR and RVV handoff are alive
```

The initramfs then starts a BusyBox shell on `/dev/console`. With the fast-boot
bitstream, use `--interactive` so the loader keeps the same CP2105 Enhanced
COM port open and forwards keyboard input after switching to 115200:

```powershell
py hardware/fpga/ara_dsa_vcu118/software/uart_load.py --port COM7 --baud 1562500 --console-baud 115200 --elf hardware/fpga/ara_dsa_vcu118/linux/artifacts/fw_jump.elf --load 0x80200000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image --load 0x80100000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/ara_vcu118.dtb --load 0x88000000:hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio --no-readback --chunk-size 65536 --interactive
```

Press `Ctrl-C` on the host to disconnect the loader; the Linux process remains
running. This is an interactive bring-up rootfs, not persistent storage and
does not yet contain llama.cpp or GGUF weights. Those still need to be added to
the initramfs or loaded into DDR by a separate high-bandwidth path.
