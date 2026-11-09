"""Ordered PV/QK arithmetic oracle using the existing independent Spike SoftFloat.

All inputs and outputs are IEEE bit patterns, not host floats. This models
arithmetic only: it neither models cycles nor proves an RTL implementation.
SoftFloat uses process-global state; use separate processes for parallel work.
"""
import hashlib
import importlib.util
from pathlib import Path

ORACLE = Path(__file__).resolve().parents[2] / "fpnew_upstream_20261009/oracle.py"
spec = importlib.util.spec_from_file_location("resident_spike_softfloat", ORACLE)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def matrix(value, width):
    require(value and value[0], "Empty matrix")
    ncols = len(value[0])
    require(all(len(row) == ncols and all(isinstance(x, int) and 0 <= x < 1 << width for x in row)
                for row in value), "Ragged matrix or invalid IEEE bits")
    return len(value), ncols


class OrderedReference:
    def __init__(self, library=oracle.LIB):
        self.library = Path(library).resolve(strict=True)
        self.sf = oracle.SoftFloat(self.library)

    def identity(self):
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ORACLE, self.library, Path(__file__))}

    def pv(self, probability, scale, seed, values, rm=0):
        heads, tokens = matrix(probability, 32)
        seed_heads, dim = matrix(seed, 16)
        value_tokens, value_dim = matrix(values, 16)
        require(heads == seed_heads and tokens == value_tokens and dim == value_dim,
                "PV shape mismatch")
        require(len(scale) == heads and all(isinstance(x, int) and 0 <= x < 1 << 32 for x in scale),
                "Invalid old-scale bits")
        require(rm in range(5), "Reserved rounding mode")
        flags = 0
        coefficient, accumulators = [], []
        for head in range(heads):
            alpha, ex = self.sf.evaluate("cast", 32, 16, rm, scale[head])
            flags |= ex
            row = []
            for value in seed[head]:
                result, ex = self.sf.evaluate("mul", 16, 16, rm, value, alpha)
                flags |= ex
                row.append(result)
            accumulators.append(row)
            converted = []
            for value in probability[head]:
                result, ex = self.sf.evaluate("cast", 32, 16, rm, value)
                flags |= ex
                converted.append(result)
            coefficient.append(converted)
        prepared_flags = flags
        prepared_seed = [row[:] for row in accumulators]
        for token in range(tokens):
            for head in range(heads):
                for dimension in range(dim):
                    result, ex = self.sf.evaluate("fma", 16, 16, rm,
                        coefficient[head][token], values[token][dimension], accumulators[head][dimension])
                    flags |= ex
                    accumulators[head][dimension] = result
        return dict(output=accumulators, fflags=flags, prepared_fflags=prepared_flags,
                    coefficient=coefficient, prepared_seed=prepared_seed)

    def qk(self, query, key, rm=0):
        heads, dim = matrix(query, 16)
        tokens, key_dim = matrix(key, 16)
        require(dim == key_dim, "QK shape mismatch")
        require(rm in range(5), "Reserved rounding mode")
        flags = 0
        widened = []
        for source in (query, key):
            destination = []
            for row in source:
                converted = []
                for value in row:
                    result, ex = self.sf.evaluate("cast", 16, 32, rm, value)
                    flags |= ex
                    converted.append(result)
                destination.append(converted)
            widened.append(destination)
        output = [[0]*tokens for _ in range(heads)]
        for dimension in range(dim):
            for head in range(heads):
                for token in range(tokens):
                    result, ex = self.sf.evaluate("fma", 32, 32, rm,
                        widened[0][head][dimension], widened[1][token][dimension], output[head][token])
                    flags |= ex
                    output[head][token] = result
        return dict(output=output, fflags=flags)
