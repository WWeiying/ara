"""Read actual Refact GGUF metadata; no tokenizer/model execution."""
from collections import Counter
import json
from pathlib import Path
import sys
from gguf import GGUFReader

r = GGUFReader(sys.argv[1])
def value(key, default=None):
    field = r.get_field(key)
    return field.contents() if field else default
arch = value('general.architecture')
heads = value(arch + '.attention.head_count')
embedding = value(arch + '.embedding_length')
tokens = r.get_field('tokenizer.ggml.tokens')
assert arch == 'refact' and tokens is not None and heads > 0
dependencies = sorted({str(Path(module.__file__).absolute()) for module in list(sys.modules.values())
                       if getattr(module, '__file__', None) and Path(module.__file__).is_file()})
print(json.dumps(dict(architecture=arch, vocabulary=len(tokens.data), layers=value(arch + '.block_count'),
    embedding=embedding, q_heads=heads, kv_heads=value(arch + '.attention.head_count_kv', heads),
    head_dim=value(arch + '.attention.key_length', embedding // heads),
    tensor_types=dict(Counter(t.tensor_type.name for t in r.tensors)),
    qkv=[(t.name, t.shape.tolist(), t.tensor_type.name) for t in r.tensors if
         t.name in ('blk.0.attn_q.weight', 'blk.0.attn_k.weight', 'blk.0.attn_v.weight')],
    metadata_reader_dependencies=dependencies), sort_keys=True))
