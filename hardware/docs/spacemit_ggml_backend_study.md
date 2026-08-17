# SpacemiT ggml-cpu Backend: Implementation Study and Lessons for Ara

## 1. Scope and source baseline

This document explains how the SpacemiT backend in `llama.cpp` accelerates
quantized inference. The focus is the complete path from a GGML tensor to an
IME matrix kernel, rather than an isolated intrinsic or a single vector dot
product.

The analysis is based primarily on the local `llama.cpp` source tree:

- Source root: `/home/wangwy/llama/llama.cpp`
- Source commit: `ea3f7acc221d9335f899c5b30420d565311de71e`
- Backend directory: `ggml/src/ggml-cpu/spacemit/`
- Build integration: `ggml/src/ggml-cpu/CMakeLists.txt`
- Backend registration: `ggml/src/ggml-cpu/ggml-cpu.cpp`

The saved article under `hardware/docs/` provides useful platform background,
but the behavioral descriptions below follow the source code. Platform claims
that cannot be established from the source are not treated as implementation
facts.

## 2. 技术路线概要

### 2.1 一句话结论

进迭时空没有停留在优化 `ggml_vec_dot_q4_K_q8_K()` 这类单输出点积，
而是把完整的 `GGML_OP_MUL_MAT` 变成了由权重预重排、activation 动态量化、
矩阵分块、专用多输出内核和可选 TCM 搬运共同组成的量化矩阵计算路径。

```text
单输出 dot 优化
    是建立正确性和基础吞吐的起点

repack + 多输出 GEMV/GEMM
    才是进迭时空主要性能路径的抽象层级
```

### 2.2 当前 Ara 路径

以 Qwen2.5-1.5B Q4_K_M 的 Decode `ffn_gate` 为例：

```text
F32 activation[1536]
  -> F32 转 Q8_K，只量化一次
Q8_K activation[1536]
  -> 循环 8960 个输出通道
     -> 读取一行原始 Q4_K 权重
     -> 调用一次 Q4_K x Q8_K、nrc=1 点积
     -> 完成该行的解包、整数乘法、归约和缩放修正
     -> 写回一个 F32 输出
F32 output[8960]
```

等价的伪代码是：

```c
quantize_row_q8_K(input_f32, activation_q8, 1536);

for (int row = 0; row < 8960; ++row) {
    output[row] = vec_dot_q4_K_q8_K(
        weight_q4_K[row], activation_q8, 1536);
}
```

这一路径已经共享了量化后的 activation，语义和结果也容易验证，但执行粒度仍是
“一行权重产生一个输出”。每个输出通道都会重新进行 Q4_K 元数据处理、权重解包、
向量归约以及 vector-to-scalar/F32 累加。

### 2.3 进迭时空路径

进迭时空把同一个算子改造成如下过程：

```text
模型加载阶段：
原始 Q4_K weight[8960,1536]
  -> 将每 32 个输出行交织重排
  -> 将 Q4_K 子块和 scale/min 元数据转换为 IME 直接消费的内部布局
  -> 重排后的权重长期保留，后续 token 直接复用

Decode 运行阶段：
F32 activation[1536]
  -> 使用 RVV 量化为内部 INT8 activation workspace
  -> 将 N=8960 划分成最多 32 个输出一组的 tile
  -> 每个 tile 调用 IME i8 x i4 的 m1 矩阵内核
     -> 一个 activation 块同时参与多个输出的计算
     -> 多个输出分别保留累加状态
     -> 在内核末端统一完成 scale/zero-point 修正
     -> 一次写回一组 F32 输出
F32 output[8960]
```

从输出布局看，`8960` 个通道对应：

```text
8960 / 32 = 280 个完整的 32-output tile
```

这里的 `280` 表示权重布局和输出分块数量，并不保证在所有线程和 TCM 配置下恰好
只有 280 次最底层函数调用。关键变化是每个内核处理多个输出，而不是一个输出。

对应的简化伪代码是：

```c
// 模型加载时只执行一次。
repack_q4_K_to_ime_32row(weight_q4_K, weight_ime);

// 每个 Decode token 执行。
quantize_activation_i8(input_f32, activation_i8, 1536);

for (int n = 0; n < 8960; n += 32) {
    ime_i8_i4_gemv_m1_n32(
        activation_i8,
        weight_ime + tile_offset(n),
        output + n);
}
```

### 2.4 Prefill 如何复用同一套机制

Prefill 不是简单地重复执行多次 Decode kernel。进迭时空在 `M>1` 时把 activation
按四行组织：

```text
F32 activation[M,K]
  -> 每次量化四行，尾部不足四行时使用单行量化
  -> M 方向最多四行一组
  -> N 方向最多 32 个输出一组
  -> 调用 m4 x n32 的矩阵内核
  -> 一个权重 tile 同时服务多个 token/activation 行
```

因此 Decode 与 Prefill：

- 共用同一套模型加载时重排的权重；
- 共用 activation workspace 和矩阵调度框架；
- Decode 选择 `m1` 内核，强调一个 activation 对大量输出的复用；
- Prefill 优先选择 `m4` 内核，同时复用 activation tile 和 weight tile。

### 2.5 Q4_K 与 Q6_K 两条路径

当前 Qwen2.5 Q4_K_M 模型的 FFN 包含两类核心计算：

```text
ffn_gate/up:
    Q4_K weight x dynamically quantized INT8 activation
    -> IME i8 x i4 matrix kernel

ffn_down:
    original Q6_K weight
    -> model-load-time dequantization and INT8 requantization
    -> Q8_0-like interleaved execution format
    -> IME i8 x i8 matrix kernel
```

两者不是互相调用的上下级 kernel，而是 `GGML_OP_MUL_MAT` 下按权重类型选择的两条
并列路径。它们共享 GGML backend、activation workspace、M/N/K 调度和 TCM 框架。

需要特别注意：Q4_K 路径主要重组 4-bit 数据及其缩放元数据；Q6_K 路径则包含
重新量化，不能把后者描述成严格无损的内存重排。

### 2.6 对 Ara 的简化实施路线

```text
阶段 1：保留并优化 nrc=1 Q4_K x Q8_K dot
  -> 建立 VLEN=1024 下可靠的单点积性能和真实数据 golden

阶段 2：实现标准 RVV 多输出 Q4_K GEMV
  -> 一次处理 4/8 个输出
  -> 共享 Q8_K activation load
  -> 减少独立归约和调用开销

阶段 3：加入模型加载时 Q4_K 权重 repack
  -> 将多个输出行交织成内核直接读取的布局
  -> 比较 4/8/16-row tile 的访存连续性和寄存器压力

阶段 4：实现 Q6_K 多输出路径
  -> 对比直接 Q6_K unpack 与预转换 INT8 两种方案
  -> 同时评估性能、模型膨胀和误差

阶段 5：实现 Prefill M-row kernel
  -> 从 m2/m4 开始
  -> 复用 weight tile，形成真正的量化 GEMM

阶段 6：依据剩余瓶颈设计 Ara DSA
  -> 可选 fused Q4 unpack-dot、packed MAC 或多输出 matrix tile
  -> 建立独立 Ara GGML backend 和标准 RVV fallback
```

这条路线保留了单点积优化的价值，但明确把最终目标放在完整量化线性算子上。
对当前模型，第一条主线应是 Q4_K FFN gate/up，第二条是 Q6_K FFN down。

## 3. Central idea

The generic quantized CPU path can be summarized as follows:

```text
GGML_OP_MUL_MAT
  -> quantize one F32 activation row
  -> iterate over output channels
  -> call an nrc=1 quantized dot product for each weight row
  -> store one F32 result per call
```

SpacemiT changes the execution granularity:

```text
model-load-time weight conversion and multi-row interleaving
  -> run-time activation quantization into an IME-oriented workspace
  -> M/N/K task partitioning
  -> multi-row, multi-output IME GEMM kernel
  -> optional TCM staging
  -> F32 output tile
```

The important optimization is therefore not simply a faster implementation of
`ggml_vec_dot_q4_K_q8_K()`. It is a coordinated backend containing:

1. a dedicated GGML buffer type;
2. model-load-time weight repacking;
3. run-time activation quantization;
4. shape- and type-dependent kernel selection;
5. Decode and Prefill scheduling;
6. IME matrix instructions;
7. standard-RVV implementations for non-matrix operators;
8. optional TCM and thread-affinity management;
9. a fallback boundary for unsupported operations.

This separation is the main architectural lesson for Ara.

## 4. Source organization

| File | Responsibility |
| --- | --- |
| `spacemit/ime.cpp` | GGML integration, tensor traits, operation dispatch, activation workspace sizing, M/N/K scheduling, TCM paths and thread handling |
| `spacemit/repack.cpp` | Conversion from GGUF quantized blocks to IME-oriented multi-row layouts |
| `spacemit/ime1_kernels.cpp` | IME1 matrix kernels |
| `spacemit/ime2_kernels.cpp` | IME2 matrix kernels, including integer matrix-dot instruction sequences |
| `spacemit/rvv_kernels.cpp` | Standard-RVV quantizers, normalization, elementwise operations, data movement and attention kernels |
| `spacemit/ime_env.cpp` | Runtime platform and capability discovery |
| `spacemit/spine_mem_pool.cpp` | Shared-memory and TCM allocation support |
| `spacemit/spine_barrier.h` | Synchronization used by paired-thread TCM paths |
| `ggml-cpu/ggml-cpu.cpp` | Registration of the SpacemiT extra buffer type with the CPU backend |
| `ggml-cpu/CMakeLists.txt` | Build flag, source inclusion, ISA extension flags and IME generation selection |

The backend is roughly fifteen thousand lines of implementation. It should be
understood as a parallel CPU backend path, not as a small patch to the generic
RISC-V vector dot products.

## 5. Build-time integration

The backend is enabled with `GGML_CPU_RISCV64_SPACEMIT`. CMake then:

- defines `GGML_USE_CPU_RISCV64_SPACEMIT`;
- defines either the IME1 or IME2 implementation selection;
- adds the backend, repack, RVV, IME and memory-management sources;
- appends standard RISC-V extensions according to GGML options;
- may append `_xsmtvdotii` for a sufficiently new GCC toolchain.

The documented build enables standard RVV and the SpacemiT backend together:

```text
GGML_CPU_RISCV64_SPACEMIT=ON
GGML_CPU_REPACK=OFF
GGML_RVV=ON
GGML_RV_ZVFH=ON
GGML_RV_ZFH=ON
GGML_RV_ZICBOP=ON
GGML_RV_ZIHINTPAUSE=ON
GGML_RV_ZBA=ON
```

`GGML_CPU_REPACK=OFF` does not mean that weights are left unrepacked. It
disables the generic CPU repack backend because the SpacemiT extra buffer owns
its own format selection and repack lifecycle.

## 6. Dedicated GGML buffer type

### 6.1 Why a buffer type is needed

GGML normally regards a quantized weight tensor as data in its declared GGUF
format. SpacemiT needs the tensor to retain its logical GGML type while its
physical bytes are arranged for IME kernels. A dedicated buffer type provides
that indirection.

`ggml_backend_cpu_get_extra_buffer_types()` registers
`ggml_backend_cpu_riscv64_spacemit_buffer_type()` when the backend is enabled.
The buffer is named `CPU_RISCV64_SPACEMIT`.

The buffer type performs three essential tasks:

1. computes the allocation size of the transformed tensor;
2. attaches an appropriate `tensor_traits` object to the tensor;
3. transforms incoming model data when `set_tensor()` is called.

Thus the model loader does not need to know the details of each IME layout.

### 6.2 Operation eligibility

The SpacemiT matrix path accepts `GGML_OP_MUL_MAT` only when all relevant
conditions hold:

- the weight tensor is two-dimensional;
- the weight resides in the SpacemiT buffer;
- a supported repack trait was selected for its type and shape;
- the activation tensor is host-accessible;
- the activation type is F32.

`GGML_OP_MUL_MAT_ID` has analogous checks for the three-dimensional expert
weight tensor used by MoE operations.

Unsupported shapes, types or storage arrangements do not become accidental IME
operations. They remain outside this backend's matrix path and can use the
normal CPU implementation.

## 7. Model-load-time weight transformation

### 7.1 Lifecycle

The weight transformation follows this sequence:

```text
GGUF tensor metadata
  -> choose tensor_traits from type, shape and IME generation
  -> allocate the transformed size
  -> load original tensor bytes
  -> tensor_traits::repack()
  -> retain the transformed tensor for all subsequent tokens
```

The repack cost is paid while loading the model, not for every inference step.
This is especially important for Decode, where the same model weights are read
for every generated token.

### 7.2 Trait parameters

The main trait template is:

```cpp
tensor_traits<BLOC_TYPE, INTER_SIZE, NB_COLS>
```

Its parameters describe:

- `BLOC_TYPE`: the original logical GGML weight type;
- `INTER_SIZE`: the K-direction block granularity consumed by the kernel;
- `NB_COLS`: the number of output columns grouped by the repacked layout.

Important currently defined traits include:

| Hardware path | Logical type | `INTER_SIZE` | Output columns |
| --- | ---: | ---: | ---: |
| IME1 | Q4_0/Q4_1/Q4_K | 32 | 16 |
| IME2 | Q4_0/Q4_1/Q4_K | 32 | 32 |
| IME2 high-precision Q4_0 | Q4_0 | 256 | 32 |
| IME2 | Q6_K | 32 | 32 |
| IME2 | Q8_0 | 32 | 32 |
| IME2 | Q2_K/Q3_K | 256 | 32 |

Not every declared trait is necessarily selected for every type. For example,
the current Q4_K selection uses the 32-by-32 IME2 trait; the 256-element
high-precision selection is present for Q4_0, not for the current Q4_K path.

### 7.3 Shape guards

For Q4_K:

- IME2 requires the output-row dimension to be divisible by 32;
- IME1 requires it to be divisible by 16.

For Q6_K on IME2, the repacker handles a partial final 32-row group by padding
unused rows with zero-valued blocks. This distinction matters when evaluating
small or irregular matrices.

### 7.4 Q4_K transformation

One Q4_K block covers 256 logical weights and contains:

- packed 4-bit values;
- a block scale and minimum;
- packed per-sub-block scale/minimum metadata.

The IME repacker divides each 256-element Q4_K block into eight 32-element
sub-blocks. For each sub-block it:

1. decodes the corresponding six-bit scale and minimum fields;
2. combines them with the block-level FP16 scale/minimum;
3. stores per-sub-block FP16 `d` and `m` values in a Q4_1-like internal block;
4. rearranges the low and high nibbles into the order expected by the matrix
   kernel;
5. interleaves the resulting blocks across 16 IME1 rows or 32 IME2 rows.

Conceptually, the layout changes from row-major blocks:

```text
row0: block0 block1 ...
row1: block0 block1 ...
...
```

to an execution-oriented group:

```text
K sub-block 0 from rows 0..31
K sub-block 1 from rows 0..31
...
```

The kernel can therefore load a weight tile for many outputs without gathering
independent blocks from many distant rows.

This is more than a byte permutation because scale/minimum metadata is also
normalized into a different internal representation. The 4-bit weight values
are reorganized rather than promoted to a higher-bit format, but FP16 metadata
conversion can still affect exact rounding.

### 7.5 Q6_K transformation

The Q6_K path is materially different. Its repacker:

1. reconstructs signed six-bit values from `ql` and `qh`;
2. applies the two Q6_K sub-block scales;
3. finds the maximum absolute scaled value for a 32-element group;
4. derives a new reflection scale;
5. requantizes the group into signed INT8;
6. stores an FP16 scale plus 32 INT8 values;
7. interleaves 32 output rows.

The resulting storage is Q8_0-like and is consumed by the IME `i8 x i8`
kernel. Unlike a pure repack, this path performs dequantization and
requantization. It therefore trades additional weight storage and possible
rounding error for a much simpler and faster execution format. Any Ara design
considering the same transformation must evaluate:

- model-memory increase;
- model-load latency;
- numerical error against the original Q6_K path;
- reduction in run-time unpack and scale-handling cost.

## 8. Run-time `GGML_OP_MUL_MAT` path

### 8.1 Matrix dimensions

The backend maps GGML tensor dimensions to:

```text
M = ne11 * ne12 * ne13  // activation rows, normally tokens or batched rows
K = ne10                // reduction/input dimension
N = ne01                // output channels
```

The mathematical operation is:

```text
C[M, N] = A[M, K] * B[K, N]
```

where `A` is supplied as F32 activation data and `B` is the transformed
quantized weight tensor.

For the current Qwen2.5 workload:

- Decode normally has `M=1` and behaves as a multi-output GEMV;
- Prefill has `M>1` and behaves as a GEMM;
- `K` is 1536 for FFN gate/up and 8960 for FFN down;
- `N` is 8960 for FFN gate/up and 1536 for FFN down.

### 8.2 Workspace sizing

Before execution, the tensor trait computes workspace for the quantized
activation. The allocation depends on:

- total activation elements;
- selected K block length;
- ordinary, K-quant or high-precision activation layout;
- optional metadata needed by `GGML_OP_MUL_MAT_ID`.

This makes activation conversion an explicit phase of the matrix operator,
rather than hidden temporary storage inside every dot product.

### 8.3 Activation quantization

The backend selects both a single-row and an optional four-row activation
quantizer.

For Decode (`M=1`):

```text
split K blocks among threads
  -> quantize disjoint portions of one activation row
  -> assemble one shared quantized row in workspace
```

For Prefill (`M>1`):

```text
divide M into groups of four rows
  -> use the four-row quantizer for complete groups
  -> use the single-row quantizer for a partial final group
```

After all threads finish quantization, a GGML thread-pool barrier ensures the
workspace is complete before matrix kernels consume it.

This phase is implemented with either standard RVV or an IME-generation-specific
quantizer. The matrix instruction does not eliminate activation quantization;
it changes the format in which the quantized activation is subsequently reused.

### 8.4 Kernel selection

The logical weight type and IME generation select the compute kernel:

| Logical weight | Activation representation | IME2 kernel family |
| --- | --- | --- |
| Q4_0/Q4_1/Q4_K | internal INT8 | `gemm_kernel_i8i4` |
| selected 256-element high-precision Q4 path | high-precision internal INT8 | `gemm_kernel_i8i4_hp` |
| Q6_K/Q8_0 | internal INT8 | `gemm_kernel_i8i8` |
| Q2_K | Q8_K-like | `gemm_kernel_i8i2k` |
| Q3_K | Q8_K-like | `gemm_kernel_i8i3k` |
| Q5 variants | internal INT8 | `gemm_kernel_i8i5` |

IME1 currently selects its `i8 x i4` kernel for the Q4 family.

The Q4_K_M model therefore does not execute the original Q4_K and Q6_K unpack
algorithms inside every output-row dot product. The model-load transformation
has already converted those weights into the formats expected by `i8 x i4` or
`i8 x i8` matrix kernels.

## 9. Multi-output and multi-row execution

### 9.1 Replacing the `nrc=1` loop

The generic path produces one output at a time:

```text
for n in outputs:
    C[n] = quantized_dot(weight_row[n], activation)
```

The IME2 Q4 layout groups 32 outputs. Its matrix kernel receives:

- the quantized activation pointer;
- one interleaved weight tile;
- optional zero-point data;
- the number of activation rows available;
- the number of valid output columns in the tile;
- the number of K blocks;
- the destination row stride.

For a Decode FFN gate with `N=8960`, the logical output dimension contains:

```text
8960 / 32 = 280 full output tiles
```

This does not imply that the entire operation makes exactly 280 low-level calls
under every thread and TCM configuration, but it accurately describes the
weight-layout and output-tile granularity. The essential point is that a kernel
call handles many outputs, not one output.

### 9.2 Decode kernel

When only one activation row is available, `gemm_kernel_i8i4()` dispatches to
the `m1` kernel. The assembly:

- loads packed/interleaved weight data;
- loads the shared quantized activation block;
- uses IME matrix-dot instructions such as `vmadot`;
- maintains accumulators for multiple output columns;
- applies weight and activation scales and zero-point correction;
- stores a vector of F32 outputs.

This is a true multi-output GEMV microkernel even though GGML calls the
operation `MUL_MAT`.

### 9.3 Prefill kernel

When at least four activation rows are available, the wrapper selects an `m4`
kernel and reports that four rows were handled. Thus Prefill reuses one weight
tile across four activation rows and computes a two-dimensional output tile.
A partial group falls back to the `m1` path until all rows are consumed.

This distinction is important: Decode and Prefill share the backend and weight
format, but they do not use an identical inner kernel.

## 10. M/N/K scheduling and multithreading

After activation quantization, the backend partitions matrix work over both M
and N. The strategy adapts according to shape:

- when `N/M` is large, it can retain a larger M span and divide N among
  threads;
- otherwise it limits an M task to a bounded number of rows;
- N partitions are rounded to the output-tile width;
- Decode can assign a broad N range because `M=1`;
- Prefill normally iterates in `NB_COLS`-wide N tiles.

The non-TCM path constructs a two-dimensional task space:

```text
task_count = ceil(M / M_stride) * ceil(N / N_stride)
```

Each worker receives a contiguous range of task IDs, converts an ID into an M
partition and an N partition, and invokes the matrix kernel until all rows in
that partition have been handled.

This software scheduling is part of the performance design. A fast matrix
instruction alone would not determine:

- how activation conversion is shared;
- how output columns are distributed;
- how partial tiles are handled;
- how multiple threads avoid redundant work.

## 11. TCM execution paths

TCM is optional. The code selects among three broad paths according to the
available per-thread TCM capacity.

### 11.1 Activation tile fits

If the relevant activation rows fit in TCM and the N partition covers the
whole output range:

1. copy the quantized activation rows to TCM;
2. walk all repacked weight tiles from normal memory;
3. execute the matrix kernel using the TCM-resident activation;
4. reuse the activation for every output tile.

This is attractive for Decode because one activation row is shared by every
output channel.

### 11.2 Weight tile fits

If one `NB_COLS` weight tile fits in TCM:

1. stage the next weight tile in TCM;
2. optionally place the activation workspace in the remaining TCM region;
3. synchronize paired threads through a dedicated barrier;
4. compute the current tile;
5. stage the following tile.

The even/odd thread structure coordinates access to the shared TCM block. This
is a platform-specific optimization and is not equivalent to an architectural
RVV feature.

### 11.3 No suitable TCM capacity

When neither useful tile fits, the backend uses the regular workspace and the
two-dimensional M/N task schedule. Functional support therefore does not
depend on TCM, although performance characteristics change.

## 12. Standard RVV remains part of the backend

SpacemiT does not route every operator through IME. A common tensor trait maps
several operators to implementations in `rvv_kernels.cpp`, including:

- F32 normalization and RMSNorm;
- F32/FP16 add, subtract, multiply and divide;
- tensor copy/contiguous conversion and permutation;
- repeat, row sum, row gather and concatenation;
- FP16 FlashAttention paths;
- activation quantization and optimized data movement used by IME kernels.

This establishes a deliberate division of labor:

```text
matrix-dense quantized work  -> IME kernels
vector-friendly auxiliary work -> standard RVV kernels
unsupported work -> generic GGML CPU path
```

It is therefore misleading to describe this as an IME-only backend. Standard
RVV supplies both standalone operators and support routines around IME.

## 13. End-to-end Q4_K call chain

The complete Q4_K path is:

```text
Build:
  enable GGML_CPU_RISCV64_SPACEMIT and IME generation

Model load:
  create Q4_K weight tensor
    -> SpacemiT buffer selects q4_k_32x32_q8_0 on IME2
    -> allocate transformed tensor size
    -> repack Q4_K into Q4_1-like 32-row-interleaved blocks

Graph execution:
  GGML_OP_MUL_MAT(weight=Q4_K, activation=F32)
    -> supports_op() accepts the operation
    -> tensor trait reports activation workspace size
    -> forward_mul_mat()
         -> map tensor dimensions to M/K/N
         -> select RVV activation quantizer
         -> select IME2 gemm_kernel_i8i4
         -> quantize one Decode row or four-row Prefill groups
         -> barrier
         -> choose TCM or regular scheduling path
         -> iterate M/N tiles
         -> execute m1 or m4 i8xi4 matrix kernel
         -> apply scales and zero-point/minimum correction
         -> store F32 output tile
```

## 14. End-to-end Q6_K call chain

The Q6_K path differs during model loading and kernel selection:

```text
Model load:
  Q6_K logical tensor
    -> reconstruct Q6 values and apply original sub-block scales
    -> requantize into Q8_0-like 32-row-interleaved blocks
    -> retain logical GGML type and transformed physical storage

Graph execution:
  GGML_OP_MUL_MAT(weight=Q6_K, activation=F32)
    -> quantize activation into internal INT8
    -> select IME2 gemm_kernel_i8i8
    -> execute Decode m1 or Prefill m4 output tiles
    -> store F32 output
```

Q4_K and Q6_K do not call each other. They are sibling weight paths sharing the
same backend scheduler and activation-workspace framework.

## 15. Application to Qwen2.5-1.5B Q4_K_M

The locally captured model has:

- hidden size: 1536;
- FFN size: 8960;
- 28 Transformer blocks;
- 12 query heads and 2 KV heads;
- Q4_K weights for Attention Q/K/output and FFN gate/up;
- Q6_K weights for Attention V and FFN down in the captured layer.

For one token and one block, the seven quantized linear layers perform these
logical matrix-vector operations:

| Layer | Weight | K | N |
| --- | --- | ---: | ---: |
| Attention Q | Q4_K | 1536 | 1536 |
| Attention K | Q4_K | 1536 | 256 |
| Attention V | Q6_K | 1536 | 256 |
| Attention output | Q4_K | 1536 | 1536 |
| FFN gate | Q4_K | 1536 | 8960 |
| FFN up | Q4_K | 1536 | 8960 |
| FFN down | Q6_K | 8960 | 1536 |

The three FFN projections account for approximately 88.2% of the MACs in
these seven linear layers. Q4_K paths account for approximately 69.7% and Q6_K
paths for approximately 30.3%.

SpacemiT's implementation matches this workload structure well:

- Q4_K FFN gate/up become 32-output `i8 x i4` tiles;
- Q6_K FFN down becomes 32-output `i8 x i8` tiles;
- one quantized activation is reused across all output tiles in Decode;
- the same repacked weights support multi-row Prefill kernels.

## 16. Comparison with the current Ara benchmark path

The current Ara standalone operator performs:

```text
for each activation column:
    quantize F32 to Q8_K once
    for each output row:
        call q4_K x q8_K or q6_K x q8_K nrc=1 dot
```

This is faithful to the generic GGML path and is useful for correctness, but it
does not reproduce SpacemiT's main optimization. In particular:

- Q4_K on VLEN=1024 now selects a dedicated single-output implementation. It
  keeps each 32-element scale domain intact, accumulates scaled products in
  i32 vector lanes, and performs one final dot-product reduction per Q4_K
  block instead of eight short reductions;
- every output row repeats setup, unpack and horizontal-reduction work;
- weights remain in their original row-major GGUF block layout;
- the kernel cannot compute several output channels in one invocation;
- no model-load-time execution layout is available;
- no tile scheduler distinguishes Decode from Prefill.

The current Ara microbenchmark should therefore remain the reference path, not
be mistaken for the final optimized organization.

## 17. What Ara should copy

The following ideas are portable to Ara even without proprietary matrix
instructions.

### 17.1 Separate storage format from execution format

Keep GGUF compatibility at the model boundary, but transform frequently used
weights once into a layout optimized for Ara. The first candidate is a Q4_K
layout interleaving 4, 8 or 16 output rows.

### 17.2 Optimize a complete quantized linear operator

Treat the optimized unit as:

```text
activation quantization
+ repacked multi-output GEMV/GEMM
+ scale/minimum correction
+ output storage
```

rather than reporting only the latency of one dot product.

### 17.3 Distinguish Decode and Prefill

- Decode: one activation row, many output channels; maximize activation reuse
  and multi-output throughput.
- Prefill: multiple activation rows; reuse both activation and weight tiles and
  use an M-row kernel.

### 17.4 Retain standard RVV fallback

An Ara backend should continue to use standard RVV for normalization,
elementwise operations, conversion and unsupported shapes. A DSA path should be
selected only when its format and shape contracts are satisfied.

### 17.5 Make capability selection explicit

Kernel selection should consider at least:

- quantization type;
- K and N divisibility;
- Decode versus Prefill M;
- architectural VLEN;
- available vector and floating-point extensions;
- whether an Ara-specific DSA is present;
- available scratchpad/cache capacity.

## 18. What Ara should not copy directly

The following details are specific to SpacemiT and require independent Ara
evaluation:

- fixed 16/32-output tiles;
- IME `vmadot`, `vmadotsu`, `vpack` and `vupack` instruction sequences;
- the IME1/IME2 feature model;
- Linux thread-affinity interfaces such as `/proc/set_ai_thread`;
- Spine TCM allocation and paired-thread barriers;
- an assumption that VLEN identifies the number of Ara lanes;
- Q6_K-to-Q8_0-like requantization without a measured accuracy and memory study;
- tile sizes tuned for a different memory hierarchy and core count.

In particular, Ara lane count is a microarchitectural parameter, not an RVV
architectural property exposed by `vlenb`. VLEN-based dispatch can choose a
legal vector implementation, but it cannot by itself identify the best Ara
lane-aware schedule.

## 19. Recommended Ara implementation sequence

### Stage 0: preserve the reference path

Retain the existing single-output Q4_K/Q6_K kernels and real captured golden
data. They are required to validate every transformed layout and optimized
kernel.

### Stage 1: improve the Q4_K single-output baseline

Implement a VLEN=1024-aware Q4_K path and reduce:

- repeated short-vector setup;
- horizontal reductions;
- vector-to-scalar transitions;
- redundant Q8_K loads;
- scale/minimum unpack overhead.

The current implementation completes the main reduction part of this stage:
the eight scaled Q4_K sub-block contributions remain in the vector domain and
share one final i32 reduction. Scale/minimum decoding is unchanged. This
establishes a stronger baseline but is not the final architecture.

### Stage 2: implement standard-RVV multi-output Q4_K GEMV

Introduce a model-load or benchmark-generation repack format that interleaves a
small number of Q4_K output rows. Start with 4 and 8 rows; measure 16 only after
register pressure is understood.

The kernel should:

1. load one Q8_K activation block;
2. load packed Q4 data for several outputs;
3. maintain separate accumulators for each output;
4. defer horizontal reduction and F32 conversion;
5. write several outputs together.

This stage tests SpacemiT's main software idea without requiring a new ISA.

### Stage 3: add Q6_K multi-output GEMV

Compare two alternatives:

- execute Q6_K directly with RVV unpack and scaling;
- convert Q6_K once to an INT8 execution format, following the SpacemiT idea.

The comparison must include cycles, transformed model size and numerical error.

### Stage 4: add Prefill M-row kernels

Reuse each repacked weight tile across several activation rows. Candidate M
tiles are 2 and 4. The best tile depends on Ara register pressure, lane count
and memory bandwidth.

### Stage 5: evaluate a DSA instruction

Only after profiling the standard-RVV multi-output implementation should a DSA
be selected. Potential targets include:

- fused packed Q4/Q8 dot accumulation;
- fused unpack plus widening MAC;
- a multi-output quantized matrix tile;
- accelerated horizontal accumulation and scale correction.

The instruction should be justified by the residual bottleneck, not selected
only because another platform provides a matrix-dot instruction.

### Stage 6: create an Ara GGML backend

Once an Ara-specific execution format or instruction exists, create a dedicated
backend with the same broad separation as SpacemiT:

```text
ggml-cpu/ara/
  backend and tensor traits
  repack formats
  standard-RVV support kernels
  optional Ara DSA kernels
  capability and shape dispatch
```

Until then, generic `arch/riscv` improvements should remain generic when they
do not depend on Ara-specific behavior.

## 20. Validation requirements

Each optimization level should be checked independently.

### 20.1 Repack validation

- Decode every transformed block with a scalar reference.
- Compare the reconstructed values or mathematically equivalent dot products.
- Cover first, middle, last and padded output rows.
- Verify scale, minimum and nibble ordering separately.

### 20.2 Kernel validation

- Compare every output against the original generic GGML kernel.
- Test Q4_K K=1536 for gate/up-like shapes.
- Test Q6_K K=8960 for down-like shapes.
- Cover full and partial output tiles.
- Cover M=1, M=2, M=4 and a non-multiple-of-four Prefill M.
- Use real captured weights and activations, not only synthetic random blocks.

### 20.3 Numerical validation

- Record absolute and relative error.
- Separate errors introduced by operation reordering from errors introduced by
  format conversion.
- For Q6_K requantization, evaluate block-level error and full-layer output
  error before accepting performance results.

### 20.4 Performance accounting

Report at least:

- one-time repack cost;
- transformed weight size;
- activation quantization cycles;
- matrix-kernel cycles;
- complete `GGML_OP_MUL_MAT` cycles;
- Decode and Prefill results separately;
- bytes read per generated output;
- speedup against the unchanged generic GGML path.

## 21. Final assessment

SpacemiT's most important contribution for this study is its choice of
abstraction boundary. It does not optimize Q4_K inference as thousands of
independent dot products. It converts the model once, quantizes activations into
a reusable workspace, partitions the full matrix operation and invokes a
multi-output matrix kernel matched to the hardware.

For Ara, the immediate optimization target remains Q4_K x Q8_K because it
covers most of the current Qwen2.5 Q4_K_M linear-layer work. However, the
SpacemiT implementation shows that the final unit of optimization should be a
repacked multi-output `GGML_OP_MUL_MAT` path. A faster `nrc=1` dot product is a
necessary baseline; it is not the complete solution.

## 22. Source index

The key local source locations used in this study are:

- `ggml/src/ggml-cpu/ggml-cpu.cpp`: registration of extra CPU buffer types.
- `ggml/src/ggml-cpu/CMakeLists.txt`: RISC-V and SpacemiT build integration.
- `ggml/src/ggml-cpu/spacemit/ime.cpp:122-234`: tensor traits and matrix dispatch.
- `ggml/src/ggml-cpu/spacemit/ime.cpp:236-543`: `forward_mul_mat()`.
- `ggml/src/ggml-cpu/spacemit/ime.cpp:1236-1395`: trait declarations and type/shape selection.
- `ggml/src/ggml-cpu/spacemit/ime.cpp:1397-1460`: tensor initialization and model-load repack.
- `ggml/src/ggml-cpu/spacemit/ime.cpp:1579-1667`: operation support checks and buffer registration.
- `ggml/src/ggml-cpu/spacemit/repack.cpp:235-290`: Q4_K to 16-row Q4_1-like layout.
- `ggml/src/ggml-cpu/spacemit/repack.cpp:928-983`: Q4_K to 32-row Q4_1-like layout.
- `ggml/src/ggml-cpu/spacemit/repack.cpp:985-1302`: Q6_K to 32-row Q8_0-like layout.
- `ggml/src/ggml-cpu/spacemit/ime2_kernels.cpp`: IME2 matrix microkernels.
- `ggml/src/ggml-cpu/spacemit/rvv_kernels.cpp`: standard-RVV support operators.
- `docs/build-riscv64-spacemit.md`: build options, platform support and published performance examples.
