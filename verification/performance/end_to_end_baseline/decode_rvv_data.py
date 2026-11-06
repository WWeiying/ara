"""Lossless native Q4_K <-> frozen GGML Q4_Kx32_ara byte layouts.

Input rows contain K/256 consecutive 144-byte blocks. Output tiles are ordered
by 32-row group, then K block, exactly as ggml_repack_q4_K_32x1_ara. Half values
are copied as bytes, never converted. Q6_K is not transformed by this helper;
its native row-major bytes remain the builder's input unchanged.
"""

Q4_BLOCK_BYTES = 144
R32_BLOCK_BYTES = 32 * Q4_BLOCK_BYTES
SOURCE_PINS = {
    "/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/"
    "e2e_output_graph_20261106_01/llama/ggml/src/ggml-cpu/repack.cpp":
        "d6a52a7f085acfca9411e006ef9db1101654e636e184c67c83b74c1c9bbd1ea3",
    "/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/"
    "e2e_output_graph_20261106_01/llama/ggml/src/ggml-cpu/repack.h":
        "598e0f993c6fbe9500f88d039ae0ea3b9dac79b9ba0e690418fee8cb1d2b0a18",
}


def _payload(data, n, k):
    if type(n) is not int or type(k) is not int:
        raise ValueError("n and k must be integers, not booleans")
    if n <= 0 or n % 32 or k <= 0 or k % 256:
        raise ValueError("Expected positive n divisible by 32 and k divisible by 256")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("Expected a bytes, bytearray or contiguous byte memoryview payload")
    view = memoryview(data)
    if view.ndim != 1 or view.itemsize != 1 or not view.c_contiguous:
        raise ValueError("Expected a one-dimensional contiguous byte payload")
    if view.nbytes != n * (k // 256) * Q4_BLOCK_BYTES:
        raise ValueError("Q4_K payload length does not match n and k exactly")
    return view.cast("B"), k // 256


def pack_q4_r32(data, n, k):
    """Return immutable x32 bytes for a native row-major N by K Q4_K tensor."""
    source, blocks = _payload(data, n, k)
    output = bytearray(len(source))
    row_stride = blocks * Q4_BLOCK_BYTES
    for row_base in range(0, n, 32):
        for block in range(blocks):
            tile = (row_base // 32 * blocks + block) * R32_BLOCK_BYTES
            first = row_base * row_stride + block * Q4_BLOCK_BYTES
            for row in range(32):
                native = first + row * row_stride
                output[tile + 2 * row:tile + 2 * row + 2] = source[native:native + 2]
                output[tile + 64 + 2 * row:tile + 66 + 2 * row] = source[native + 2:native + 4]
            for native_start, length, packed_start in ((4, 12, 128), (16, 128, 512)):
                for byte in range(length):
                    start = first + native_start + byte
                    target = tile + packed_start + byte * 32
                    output[target:target + 32] = bytes(source[start:start + 32 * row_stride:row_stride])
    return bytes(output)


def unpack_q4_r32(data, n, k):
    """Return immutable native row-major bytes, reversing pack_q4_r32 exactly."""
    source, blocks = _payload(data, n, k)
    output = bytearray(len(source))
    for row in range(n):
        for block in range(blocks):
            tile = (row // 32 * blocks + block) * R32_BLOCK_BYTES
            lane = row % 32
            native = (row * blocks + block) * Q4_BLOCK_BYTES
            output[native:native + 2] = source[tile + 2 * lane:tile + 2 * lane + 2]
            output[native + 2:native + 4] = source[tile + 64 + 2 * lane:tile + 66 + 2 * lane]
            output[native + 4:native + 16] = bytes(source[tile + 128 + lane:tile + 512 + lane:32])
            output[native + 16:native + 144] = bytes(source[tile + 512 + lane:tile + 4608 + lane:32])
    return bytes(output)
