"""Real ONNX Runtime Q/DQ MatMul versus QBS import/plan/instruction reference.

The ONNX weights use UINT8 containers with 4/5/8 significant bits, not ORT's
private MatMulNBits layout. Activations are explicitly INT8 Q/DQ: this is NOT
an equivalence claim for weight-only W4A16 or W4A32 inference.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import subprocess

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import onnxruntime as ort


class GroupedInteger(C.Structure):
    _fields_ = [
        ("quants", C.c_void_p), ("quant_bytes", C.c_size_t),
        ("row_stride_bytes", C.c_size_t), ("scales", C.c_void_p),
        ("scale_count", C.c_size_t), ("zero_points", C.c_void_p),
        ("zero_point_count", C.c_size_t), ("rows", C.c_uint32),
        ("k_elements", C.c_uint32), ("group_elements", C.c_uint32),
        ("bits", C.c_uint8), ("signed_quants", C.c_uint8),
    ]


def pack(values, scales, zero, bits, group, signed=False):
    n, k = values.shape
    raw = np.zeros((n, (k * bits + 7) // 8), dtype=np.uint8)
    for i in range(k):
        u = values[:, i].astype(np.int32) & ((1 << bits) - 1)
        byte, offset = divmod(i * bits, 8)
        raw[:, byte] |= ((u << offset) & 255).astype(np.uint8)
        if offset + bits > 8:
            raw[:, byte + 1] |= (u >> (8 - offset)).astype(np.uint8)
    scales = np.ascontiguousarray(scales, dtype=np.float32)
    zero = np.ascontiguousarray(zero, dtype=np.int16)
    descriptor = GroupedInteger(raw.ctypes.data, raw.nbytes, raw.strides[0],
        scales.ctypes.data, scales.size, zero.ctypes.data, zero.size,
        n, k, group, bits, int(signed))
    return descriptor, (raw, scales, zero)


def model(m, n, k, bits, group):
    rng = np.random.default_rng(8097 + m + n + k + bits)
    w = rng.integers(0, 1 << bits, size=(n, k), dtype=np.uint8)
    x = rng.integers(-8, 9, size=(m, k), dtype=np.int8)
    ws = rng.choice(np.array([0.125, 0.25], np.float32), (n, k // group))
    xs = rng.choice(np.array([0.125, 0.25], np.float32), (m, k // 32))
    wz = np.full_like(ws, 1 << (bits - 1), dtype=np.uint8)
    xz = np.zeros_like(xs, dtype=np.int8)
    initializers = [numpy_helper.from_array(a, name) for name, a in (
        ("wq", w.reshape(-1, group)), ("ws", ws.reshape(-1)),
        ("wz", wz.reshape(-1)), ("xs", xs.reshape(-1)),
        ("xz", xz.reshape(-1)), ("wshape", np.array([n, k], np.int64)),
        ("xshape", np.array([m, k], np.int64)))]
    nodes = [
        helper.make_node("DequantizeLinear", ["wq", "ws", "wz"], ["wdq"], axis=0),
        helper.make_node("Reshape", ["wdq", "wshape"], ["w"]),
        helper.make_node("Transpose", ["w"], ["wt"], perm=[1, 0]),
        helper.make_node("DequantizeLinear", ["xq", "xs", "xz"], ["xdq"], axis=0),
        helper.make_node("Reshape", ["xdq", "xshape"], ["x"]),
        helper.make_node("MatMul", ["x", "wt"], ["out"]),
    ]
    graph = helper.make_graph(nodes, "grouped_integer_matmul", [
        helper.make_tensor_value_info("xq", TensorProto.INT8, [m * k // 32, 32])], [
        helper.make_tensor_value_info("out", TensorProto.FLOAT, [m, n])], initializers)
    result = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 19)], ir_version=9)
    onnx.checker.check_model(result)
    return result, x


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, default=Path(__file__).resolve().parents[1] / "build/onnx")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    library = build / "libqbs_onnx_test.so"
    subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-fno-fast-math", "-ffp-contract=off", "-frounding-math",
        "-I" + str(root / "software/qbs/include"),
        *[str(root / s) for s in ("software/qbs/tests/onnx_bridge.c",
            "software/qbs/src/qbs_format.c", "software/qbs/src/qbs_runtime.c",
            "verification/qbs/qbs_ref.c")], "-lm", "-o", str(library)], check=True)
    lib = C.CDLL(str(library))
    run = lib.qbs_onnx_test_matmul
    run.argtypes = [C.POINTER(GroupedInteger), C.POINTER(GroupedInteger), C.c_uint,
                   C.c_void_p, C.c_size_t, C.POINTER(C.c_uint64)]
    run.restype = C.c_int
    lib.qbs_onnx_test_profile.argtypes = [C.c_uint]
    lib.qbs_onnx_test_profile.restype = C.c_uint
    results = []
    for bits in (4, 5, 8):
        profile = lib.qbs_onnx_test_profile(bits)
        for m, n, k, group in ((1, 5, 64, 32), (2, 33, 128, 64),
                               (3, 35, 256, 128), (5, 17, 256, 256),
                               (9, 5, 64, 64), (2, 5, 8256, 64)):
            graph, x = model(m, n, k, bits, group)
            # Parse the serialized model's actual initializers, not side data.
            path = build / f"w{bits}_m{m}_n{n}_k{k}_g{group}.onnx"
            onnx.save(graph, path)
            tensors = {t.name: numpy_helper.to_array(t) for t in onnx.load(path).graph.initializer}
            weight, wr = pack(tensors["wq"].reshape(n, k), tensors["ws"], tensors["wz"], bits, group)
            activation, ar = pack(x, tensors["xs"], tensors["xz"], 8, 32, signed=True)
            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
            expected = session.run(None, {"xq": x.reshape(-1, 32)})[0]
            actual = np.zeros((m, n), dtype=np.float32)
            commands = C.c_uint64()
            status = run(C.byref(weight), C.byref(activation), profile, actual.ctypes.data,
                         actual.size, C.byref(commands))
            if status:
                raise AssertionError(f"QBS status={status}, bits={bits}, shape={(m,n,k)}")
            np.testing.assert_array_equal(actual, expected)
            results.append(dict(bits=bits, m=m, n=n, k=k, group=group,
                commands=commands.value, max_abs_error=float(np.max(np.abs(actual-expected))), status="PASS"))
    report = dict(scope="ONNX Q/DQ MatMul vs QBS instruction reference; not a native ORT EP",
                  onnx=onnx.__version__, onnxruntime=ort.__version__, cases=results)
    (build / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"ONNX Runtime: {len(results)} grouped-integer MatMul cases PASS; {build / 'results.json'}")


if __name__ == "__main__":
    main()
