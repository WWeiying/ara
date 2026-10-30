#!/usr/bin/env python3
"""Derive an isolated hint-first candidate from the exact installed cache."""
import argparse
import hashlib
import json
from pathlib import Path


def transform(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Ambiguous cache anchor: '+old)
        text = text.replace(old, new)

    # Rename only the namespace declaration and its closing comment.
    if text.count('ggml_riscv_q8_K_cache') != 2:
        raise ValueError('Unexpected namespace references')
    text = text.replace('ggml_riscv_q8_K_cache', 'ggml_riscv_q8_K_cache_hint')
    replace('''    size_t find(const key &k,const void *input,size_t in,size_t out) {
        for(size_t i=0;i<Slots;++i) {
            const auto &e=entries_[i];
            if(!e.valid || !same(e.identity,k) || e.input_bytes!=in || e.output_bytes!=out) continue;
            stats_.comparison_bytes_requested+=in;
            if(ggml_riscv_byte_ops::equal(e.data.get(),input,in)) return i;
        }
        return Slots;
    }''', '''    size_t find(const key &k,const void *input,size_t in,size_t out,size_t *hint) {
        const size_t preferred=hint ? *hint:Slots;
        const auto matches=[&](size_t i) {
            const auto &e=entries_[i];
            if(!e.valid || !same(e.identity,k) || e.input_bytes!=in || e.output_bytes!=out) return false;
            stats_.comparison_bytes_requested+=in;
            return ggml_riscv_byte_ops::equal(e.data.get(),input,in);
        };
        if(preferred<Slots && matches(preferred)) return preferred;
        for(size_t i=0;i<Slots;++i)
            if(i!=preferred && matches(i)) return i;
        return Slots;
    }''')
    replace('bool get(const key &k,const void *input,size_t in,void *output,size_t out,unsigned &flags) {',
            'bool get(const key &k,const void *input,size_t in,void *output,size_t out,unsigned &flags,size_t *hint=nullptr) {')
    replace('size_t i=find(k,input,in,out);', 'size_t i=find(k,input,in,out,hint);\n        if(hint) *hint=i;')
    replace('bool put(const key &k,const void *input,size_t in,const void *output,size_t out,unsigned flags) {',
            'bool put(const key &k,const void *input,size_t in,const void *output,size_t out,unsigned flags,size_t *hint=nullptr) {')
    replace('size_t duplicate=find(k,input,in,out);',
            'size_t duplicate=find(k,input,in,out,hint);\n        if(hint) *hint=duplicate;')
    replace('stats_.conflicts;erase(duplicate);return false;',
            'stats_.conflicts;erase(duplicate);if(hint) *hint=Slots;return false;')
    replace('retained_+=total;++stats_.stores;stats_.copied_payload_bytes+=total;return true;',
            'retained_+=total;++stats_.stores;stats_.copied_payload_bytes+=total;\n        if(hint) *hint=slot;\n        return true;')
    return text


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();source=args.source.resolve(strict=True)
    raw=source.read_bytes();candidate=transform(raw.decode())
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'original_cache.h').write_bytes(raw)
    (args.output/'hinted_cache.h').write_text(candidate)
    pins={str(path.resolve()):hashlib.sha256(path.read_bytes()).hexdigest() for path in
          [source,Path(__file__),args.output/'original_cache.h',args.output/'hinted_cache.h']}
    (args.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')


if __name__=='__main__': main()
