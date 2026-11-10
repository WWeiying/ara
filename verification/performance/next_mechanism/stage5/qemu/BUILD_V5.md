# Internal-FDT Configuration V5

BUILD02 reached Meson successfully but failed target selection. Both accepted
old and BUILD02 probes found no system libfdt. The old build selected the
populated internal dtc subproject. With --disable-download, QEMU maps automatic
FDT fallback to disabled (meson.build:2072-2097), even when dtc exists.

V5 adds exactly --enable-fdt=internal to V4's configure argv. It retains
--disable-download, Python 3.11, explicit Ninja and the unchanged minimal tool
environment. No re-extraction, source variant, metadata patch or library install.
prepare03 and toolenv02 remain immutable; V4's three files remain sealed.

The static comparison covers twelve Meson metadata files in the six subprojects
used by the accepted build: dtc, libvhost-user, libvduse, keycodemapdb,
berkeley-softfloat-3 and berkeley-testfloat-3. They match prepared03. The target
requires FDT and an accelerator; TCG is enabled. The other mandatory host
dependencies passed BUILD02's Meson probes. The relevant Meson nodownload
selection exception is FDT; Rust is disabled. This is configuration/static
evidence, not a successful compilation or a general build-closure proof.

Parent launches build_v5.py build --output <fresh BUILD03> --service <unit>
--reviewed-inputs-sha256 <identity SHA> as direct systemd MainPID. Bounds remain
900 seconds configure and 1800 seconds Ninja -j4. The downstream API remains
checked_build(build_dir, reviewed_build_sha256); it now requires schema
stage5-qemu-build-v5, the exact internal-FDT argv and the six-file validator
closure (three V5 files plus three sealed V4 files). No V4 acceptance is weakened.
