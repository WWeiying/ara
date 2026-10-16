#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../../../.." && pwd)
OUT=${OUT:-"$SCRIPT_DIR/qwen25_eval/out"}
ARTIFACTS=${ARTIFACTS:-"$SCRIPT_DIR/qwen25_eval/artifacts"}
BASE_ARTIFACTS=${BASE_ARTIFACTS:-"$SCRIPT_DIR/artifacts"}
SDK=${SDK:-/home/wangwy/openproject/cva6/cva6-sdk}
CROSS_COMPILE=${CROSS_COMPILE:-"$SDK/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-"}
CC=${CC:-"${CROSS_COMPILE}gcc"}
STRIP=${STRIP:-"${CROSS_COMPILE}strip"}
DTC=${DTC:-dtc}
LLAMA_SRC=${LLAMA_SRC:-/home/wangwy/llama/llama.cpp}
LLAMA_BUILD_DIR=${LLAMA_BUILD_DIR:-/home/wangwy/llama/llama.cpp/build-rv64-ara-dsa-qwen25-eval}
LLAMA_SIMPLE=${LLAMA_SIMPLE:-"$LLAMA_BUILD_DIR/bin/llama-simple"}
QWEN_MODEL=${QWEN_MODEL:-/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}
QBS_RUNTIME_DIR=${QBS_RUNTIME_DIR:-"$REPO_ROOT/software/qbs"}
AKV_RUNTIME_DIR=${AKV_RUNTIME_DIR:-"$REPO_ROOT/software/akv"}
JOBS=${JOBS:-$(nproc)}

FW_ADDR=0x80000000
DTB_ADDR=0x80100000
KERNEL_ADDR=0x80200000
INITRD_ADDR=0x88000000

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

for command in "$CC" "$STRIP" "$DTC" cpio cmake; do
    command -v "$command" >/dev/null 2>&1 || die "missing command: $command"
done
for file in "$BASE_ARTIFACTS/fw_jump.elf" "$BASE_ARTIFACTS/Image" \
    "$BASE_ARTIFACTS/ara_vcu118.dtb" "$BASE_ARTIFACTS/initramfs.cpio" \
    "$QWEN_MODEL"; do
    [[ -f "$file" ]] || die "missing input: $file"
done
[[ -f "$SDK/buildroot/output/build/opensbi-1.7/Makefile" ]] || \
    die "OpenSBI source not found under $SDK"

if [[ ! -x "$LLAMA_SIMPLE" ]]; then
    [[ -f "$LLAMA_SRC/CMakeLists.txt" ]] || die "llama.cpp source not found: $LLAMA_SRC"
    cmake -S "$LLAMA_SRC" -B "$LLAMA_BUILD_DIR" \
        -DCMAKE_TOOLCHAIN_FILE=/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_EXE_LINKER_FLAGS=-static \
        -DGGML_NATIVE=OFF -DGGML_RVV=ON \
        -DGGML_RV_ZFH=ON -DGGML_RV_ZVFH=ON \
        -DGGML_RV_ZICBOP=OFF -DGGML_RV_ZIHINTPAUSE=OFF \
        -DGGML_OPENMP=OFF -DGGML_BACKEND_DL=OFF -DGGML_LLAMAFILE=OFF \
        -DGGML_RISCV_QBS=ON -DGGML_RISCV_QBS_RUNTIME_DIR="$QBS_RUNTIME_DIR" \
        -DGGML_RISCV_AKV=ON -DGGML_RISCV_AKV_RUNTIME_DIR="$AKV_RUNTIME_DIR" \
        -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_TOOLS=OFF \
        -DLLAMA_BUILD_SERVER=OFF -DBUILD_SHARED_LIBS=OFF
    cmake --build "$LLAMA_BUILD_DIR" --target llama-simple -j"$JOBS"
fi
[[ -x "$LLAMA_SIMPLE" ]] || die "llama-simple was not built: $LLAMA_SIMPLE"

mkdir -p "$OUT"
rm -rf "$OUT/initramfs" "$OUT/opensbi-fw-jump" "$OUT/ara_vcu118.dts"
mkdir -p "$OUT/initramfs"
(cd "$OUT/initramfs" && cpio -idmu --quiet < "$BASE_ARTIFACTS/initramfs.cpio")

mkdir -p "$OUT/initramfs/usr/bin" "$OUT/initramfs/model" \
    "$OUT/initramfs/eval/results" "$OUT/initramfs/eval/prompts"
cp "$LLAMA_SIMPLE" "$OUT/initramfs/usr/bin/llama-simple"
"$CC" -static -O2 -Wall -Wextra -o "$OUT/initramfs/usr/bin/model-rx" \
    "$SCRIPT_DIR/qwen25_eval/model_rx.c"
"$STRIP" --strip-debug "$OUT/initramfs/usr/bin/llama-simple" \
    "$OUT/initramfs/usr/bin/model-rx"
cp "$SCRIPT_DIR/qwen25_eval/qwen-eval" "$OUT/initramfs/usr/bin/qwen-eval"
chmod 0755 "$OUT/initramfs/usr/bin/llama-simple" \
    "$OUT/initramfs/usr/bin/model-rx" "$OUT/initramfs/usr/bin/qwen-eval"
cp "$SCRIPT_DIR/qwen25_eval/init" "$OUT/initramfs/init"
chmod 0755 "$OUT/initramfs/init"
for prompt in 64 128 512 2048; do
    cp "$SCRIPT_DIR/qwen25_eval/prompts/p${prompt}.txt" \
        "$OUT/initramfs/eval/prompts/p${prompt}.txt"
done

cat > "$OUT/initramfs/eval/README" <<'EOF'
Qwen2.5-1.5B-Instruct-Q4_K_M evaluation image.
The model is uploaded after Linux boot with software/model_push.py.
Use qwen-eval rvv, qbs, akv, or qbs-akv.
EOF

(
    cd "$OUT/initramfs"
    find . -print0 | cpio --null -o --format=newc > "$OUT/initramfs.cpio"
)

initrd_size=$(stat -c '%s' "$OUT/initramfs.cpio")
initrd_end=$(printf '0x%x' $((INITRD_ADDR + initrd_size)))
sed \
    -e "s/__INITRD_START__/$INITRD_ADDR/g" \
    -e "s/__INITRD_END__/$initrd_end/g" \
    "$SCRIPT_DIR/ara_vcu118.dts.in" > "$OUT/ara_vcu118.dts"
"$DTC" -I dts -O dtb -o "$OUT/ara_vcu118.dtb" "$OUT/ara_vcu118.dts"

make -C "$SDK/buildroot/output/build/opensbi-1.7" O="$OUT/opensbi-fw-jump" \
    PLATFORM=generic PLATFORM_RISCV_XLEN=64 \
    CROSS_COMPILE="$CROSS_COMPILE" \
    FW_TEXT_START="$FW_ADDR" FW_FDT_PATH="$OUT/ara_vcu118.dtb" \
    FW_JUMP=y FW_DYNAMIC=n FW_PAYLOAD=n \
    FW_JUMP_ADDR="$KERNEL_ADDR" FW_JUMP_FDT_ADDR="$DTB_ADDR"
cp "$BASE_ARTIFACTS/Image" "$OUT/Image"
cp "$OUT/opensbi-fw-jump/platform/generic/firmware/fw_jump.elf" "$OUT/fw_jump.elf"
"$STRIP" --strip-debug "$OUT/fw_jump.elf"

(
    cd "$OUT"
    sha256sum fw_jump.elf Image ara_vcu118.dtb initramfs.cpio > SHA256SUMS
)
model_size=$(stat -c '%s' "$QWEN_MODEL")
model_sha=$(sha256sum "$QWEN_MODEL" | awk '{print $1}')
cat > "$OUT/LOAD_LAYOUT.txt" <<EOF
fw_jump.elf     @ $FW_ADDR
ara_vcu118.dtb  @ $DTB_ADDR
Image           @ $KERNEL_ADDR
initramfs.cpio  @ $INITRD_ADDR
EOF
cat > "$OUT/MODEL_MANIFEST.txt" <<EOF
model=Qwen2.5-1.5B-Instruct-Q4_K_M
source=$QWEN_MODEL
target=/model/qwen2.5-1.5b-instruct-q4_k_m.gguf
size=$model_size
sha256=$model_sha
transfer=software/model_push.py --port COM6 --model <model.gguf>
modes=rvv,qbs,akv,qbs-akv
EOF

rm -rf "$ARTIFACTS"
mkdir -p "$ARTIFACTS"
cp "$OUT/fw_jump.elf" "$OUT/Image" "$OUT/ara_vcu118.dtb" \
    "$OUT/initramfs.cpio" "$OUT/LOAD_LAYOUT.txt" "$OUT/MODEL_MANIFEST.txt" \
    "$ARTIFACTS/"
(
    cd "$ARTIFACTS"
    sha256sum fw_jump.elf Image ara_vcu118.dtb initramfs.cpio > SHA256SUMS
)

printf '\nQwen25 evaluation artifacts generated in %s\n' "$OUT"
printf 'Windows/package artifacts: %s\n' "$ARTIFACTS"
cat "$OUT/LOAD_LAYOUT.txt"
printf 'model size: %s bytes\nmodel sha256: %s\n' "$model_size" "$model_sha"
