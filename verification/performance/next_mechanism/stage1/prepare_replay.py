#!/usr/bin/env python3
"""Derive bounded replays from the pinned board frontend, never overwrite it."""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA = '3cc13b01c6fbdd814d501883f266c89d482cbd88a83ee4cfe06d8e8bb10d5cf0'


def transform(raw, probe):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('Unexpected replay source; review before adapting')
    text = raw.decode()

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Ambiguous frontend anchor: ' + old)
        text = text.replace(old, new)

    replace('if (argc != 7)', 'if (argc != 8)')
    replace('qbs_only|qbs_akv");', 'qbs_only|qbs_akv STEPS");')
    replace('    const uint64_t main_begin = now_ns();', '''    char *step_end = nullptr;
    const unsigned long requested_steps = std::strtoul(argv[7], &step_end, 10);
    if (!argv[7][0] || *step_end || requested_steps < 1 || requested_steps > 32)
        throw std::runtime_error("STEPS must be 1..32");
    const uint64_t main_begin = now_ns();''')
    replace('if (history.size()<32)', 'if (history.size()<requested_steps)')
    replace('Reference continuation shorter than 32 tokens', 'Reference continuation shorter than requested steps')
    replace('history.resize(32);', 'history.resize(requested_steps);')
    replace('std::printf("STAGE1_PROGRESS decode=%u/32 ns=%llu\\n",step+1,',
            'std::printf("STAGE1_PROGRESS decode=%u/%zu ns=%llu\\n",step+1,history.size(),')
    if not probe:
        return text
    replace('#include "path_counts.hpp"', '#include "path_counts.hpp"\n#include "node_probe.h"')
    replace('    const auto inference_begin=now_ns();', '''    const char *mode = std::getenv("STAGE1_NODE_TIMING");
    if (!mode || (std::string(mode)!="0" && std::string(mode)!="1"))
        throw std::runtime_error("STAGE1_NODE_TIMING must be 0 or 1");
    const int active = mode[0]=='1';
    std::vector<stage1_node_probe_record> node_storage(65536);
    if (stage1_node_probe_init(node_storage.data(), node_storage.size()))
        throw std::runtime_error("Probe initialization failed");
    auto probe_begin = [&](unsigned id, const char *phase) {
        if (stage1_node_probe_phase_begin(id, phase, active, 1))
            throw std::runtime_error("Probe begin failed");
    };
    auto probe_finish = [&](unsigned id, int rc) {
        const int status = stage1_node_probe_phase_finish(rc==0);
        const std::string path=out+"/nodes_"+std::to_string(id)+".jsonl";
        FILE *nodes=std::fopen(path.c_str(),"wbx");
        if (!nodes) throw std::runtime_error("Fresh node destination required");
        const int dumped=stage1_node_probe_dump(nodes);
        const int closed=std::fclose(nodes);
        if (status || dumped || closed) throw std::runtime_error("Probe record invalid");
    };
    const auto inference_begin=now_ns();''')
    replace('    auto start=now_ns();', '    probe_begin(0,"prefill");\n    auto start=now_ns();')
    replace('    const auto prefill_ns=now_ns()-start;',
            '    const auto prefill_ns=now_ns()-start;\n    probe_finish(0,prefill_rc);')
    replace('        stage1_paths={};start=now_ns();',
            '        stage1_paths={};probe_begin(step+1,"decode");start=now_ns();')
    replace('        const auto duration=now_ns()-start;',
            '        const auto duration=now_ns()-start;\n        probe_finish(step+1,rc);')
    replace('    llama_perf_context_print(ctx);', '''    result["node_timing_active"]=bool(active);
    result["node_metadata_capture"]=true;
    result["inference_window_includes_probe_export"]=true;
    llama_perf_context_print(ctx);''')
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    raw = args.source.read_bytes()
    versions = {name: transform(raw, enabled) for name, enabled in
                [('replay_plain.cpp', False), ('replay_probe.cpp', True)]}
    args.output.mkdir(parents=True, exist_ok=False)
    for name, text in versions.items():
        (args.output/name).write_text(text)
    (args.output/'preparation.json').write_text(json.dumps(dict(
        state='PREPARED_NOT_COMPILED', source=str(args.source.resolve()),
        source_sha256=SOURCE_SHA, outputs={name: hashlib.sha256(text.encode()).hexdigest()
                                         for name, text in versions.items()}), indent=2)+'\n')


if __name__ == '__main__':
    main()
