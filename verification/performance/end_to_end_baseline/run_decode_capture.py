#!/usr/bin/env python3
"""Capture actual first Decode projection, FFN and vocabulary inputs."""
import argparse

from capture_model_inputs import run_capture
from decode_capture import check
from run_projection_capture_v3 import HERE


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',required=True)
    args = parser.parse_args()
    specs = [('blk.0.'+name+'.weight',name+'.bin',k,n) for name,k,n in
             (('attn_q',2048,2048),('attn_k',2048,1024),('attn_v',2048,1024),
              ('ffn_gate',2048,6144),('ffn_up',2048,6144),('ffn_down',6144,2048))]
    specs.append(('output.weight','vocabulary.bin',2048,151936))
    run_capture(args.output,HERE/'capture_decode.cpp',check,specs,
                'REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED',2400)


if __name__ == '__main__': main()
