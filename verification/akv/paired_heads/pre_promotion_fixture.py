"""Immutable input for historical fail-closed candidate-generator tests."""
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
SOURCE_SHA256 = 'f345307eea2bcc888d9df951ff2c14982ff6821cbf0d00d870c04492052c75cb'


def source():
    value = subprocess.check_output(['git','show',
        'e54d2b35:software/akv/src/akv_v2_native_riscv.c'],cwd=ROOT)
    if hashlib.sha256(value).hexdigest() != SOURCE_SHA256:
        raise ValueError('Historical generator fixture does not match sealed source')
    return value.decode('ascii')
