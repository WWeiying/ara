#!/usr/bin/env python3
"""Produce a prospective standalone Makefile patch, never apply it or run EDA."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATOR = '$(ROOT)/verification/akv/canonical_promotion/generate_standalone.py'


def edits(kind):
    if kind == 'qbs':
        old_sources = 'RTL_ENGINE_SOURCES := $(RTL_SOURCES) $(abspath qbs_engine_tb.sv)'
        return [
            ('RTL_ENGINE_DEFINES ?=\n', 'RTL_ENGINE_DEFINES ?=\nRTL_STANDALONE_GENERATOR := ' + GENERATOR + '\n'),
            ('RTL_INCLUDES := +incdir+$(ROOT)/hardware/deps/common_cells/include \\\n',
             'RTL_INCLUDES := +incdir+$(ROOT)/hardware/include \\\n\t+incdir+$(ROOT)/hardware/deps/common_cells/include \\\n'),
            ('\t$(ROOT)/hardware/src/vlsu/qbs/qbs_read_engine.sv \\\n',
             '\t$(ROOT)/hardware/src/vlsu/qbs/qbs_read_engine.sv \\\n\t$(ROOT)/hardware/src/vlsu/qbs_akv_shared_reader.sv \\\n'),
            (old_sources, 'RTL_ENGINE_SOURCES := $(RTL_SOURCES) \\\n'
             '\t$(abspath $(RTL_ENGINE_BUILD)/standalone/composed_engine.sv) \\\n'
             '\t$(abspath $(RTL_ENGINE_BUILD)/standalone/original_suite.sv)'),
            ('rtl-engine-compile: qbs_command_vectors.txt $(RTL_ENGINE_SOURCES)\n\tmkdir -p $(RTL_ENGINE_BUILD)\n',
             'rtl-engine-compile: qbs_command_vectors.txt $(RTL_SOURCES) $(abspath qbs_engine_tb.sv) $(RTL_STANDALONE_GENERATOR)\n'
             '\tmkdir -p $(RTL_ENGINE_BUILD)\n'
             '\tpython3 -B $(RTL_STANDALONE_GENERATOR) --source-root $(ROOT) --kind qbs \\\n'
             '\t\t--tb $(abspath qbs_engine_tb.sv) --output $(abspath $(RTL_ENGINE_BUILD)/standalone)\n'),
        ]
    if kind == 'akv':
        return [
            ('TB := $(abspath akv_engine_tb.sv)\n',
             'TB := $(abspath akv_engine_tb.sv)\nRTL_STANDALONE_GENERATOR := ' + GENERATOR + '\n'
             'COMPOSED_TB := $(abspath $(BUILD)/standalone/composed_engine.sv) $(abspath $(BUILD)/standalone/original_suite.sv)\n'
             'MACRO_COMPOSED_TB := $(abspath $(MACRO_BUILD)/standalone/composed_engine.sv) $(abspath $(MACRO_BUILD)/standalone/original_suite.sv)\n'),
            ('rtl-compile: $(FILELIST) $(TB) $(RTL_EXTRA_SOURCES)\n',
             'rtl-compile: $(FILELIST) $(TB) $(RTL_EXTRA_SOURCES) $(RTL_STANDALONE_GENERATOR)\n'
             '\tpython3 -B $(RTL_STANDALONE_GENERATOR) --source-root $(ROOT) --kind akv \\\n'
             '\t\t--tb $(TB) --output $(abspath $(BUILD)/standalone)\n'),
            ('$(RTL_EXTRA_DEFINES) -f $(FILELIST) $(TB) $(RTL_EXTRA_SOURCES) -top akv_engine_tb',
             '$(RTL_EXTRA_DEFINES) -f $(FILELIST) $(COMPOSED_TB) $(RTL_EXTRA_SOURCES) -top akv_engine_tb'),
            ('rtl-macro-compile: $(MACRO_FILELIST) $(TB) $(MACRO_MODEL)\n',
             'rtl-macro-compile: $(MACRO_FILELIST) $(TB) $(MACRO_MODEL) $(RTL_EXTRA_SOURCES) $(RTL_STANDALONE_GENERATOR)\n'
             '\tpython3 -B $(RTL_STANDALONE_GENERATOR) --source-root $(ROOT) --kind akv \\\n'
             '\t\t--tb $(TB) --output $(abspath $(MACRO_BUILD)/standalone)\n'),
            ('-l compile.log -f $(MACRO_FILELIST) $(MACRO_MODEL) $(TB) \\\n',
             '-l compile.log $(RTL_EXTRA_DEFINES) -f $(MACRO_FILELIST) $(MACRO_MODEL) $(MACRO_COMPOSED_TB) $(RTL_EXTRA_SOURCES) \\\n'),
            ('synth-wrapper-compile: $(MACRO_FILELIST) $(MACRO_MODEL) $(SYNTH_WRAPPER)\n',
             'synth-wrapper-compile: $(MACRO_FILELIST) $(MACRO_MODEL) $(SYNTH_WRAPPER) $(RTL_EXTRA_SOURCES)\n'),
            ('+define+TARGET_SRAM_MC +lint=TFIPC-L -l compile.log \\\n',
             '+define+TARGET_SRAM_MC $(RTL_MACRO_VCS_FLAGS) +lint=TFIPC-L -l compile.log \\\n'),
            ('-f $(MACRO_FILELIST) $(MACRO_MODEL) $(SYNTH_WRAPPER) \\\n',
             '$(RTL_EXTRA_DEFINES) -f $(MACRO_FILELIST) $(MACRO_MODEL) $(SYNTH_WRAPPER) $(RTL_EXTRA_SOURCES) \\\n'),
        ]
    raise ValueError('Known engine required')


def render(text, kind):
    output = text
    for before, after in edits(kind):
        if output.count(before) != 1:
            raise ValueError('Original Makefile anchor changed/duplicated: ' + before)
        output = output.replace(before, after, 1)
    restored = output
    for before, after in reversed(edits(kind)):
        if restored.count(after) != 1:
            raise ValueError('Ambiguous inverse patch')
        restored = restored.replace(after, before, 1)
    if restored != text:
        raise ValueError('Unrelated Makefile change')
    return output


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(root, output):
    root = root.resolve(strict=True)
    candidates, originals = {}, {}
    for kind in ('qbs', 'akv'):
        name = 'verification/' + kind + '/Makefile'
        originals[name] = (root / name).read_text()
        candidates[name] = render(originals[name], kind)
    output.mkdir(parents=True, exist_ok=False)
    patch = ''
    for name in originals:
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(candidates[name])
        patch += ''.join(difflib.unified_diff(originals[name].splitlines(keepends=True),
                    candidates[name].splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name))
    patch_path = output / 'standalone_makefiles.patch'
    patch_path.write_text(patch)
    own = [HERE / name for name in ('standalone_makefiles.py', 'generate_standalone.py',
                                   'test_standalone_makefiles.py', 'STANDALONE_PACKAGING.md')]
    report = dict(state='STANDALONE_MAKEFILE_PATCH_NOT_APPLIED', production_promoted=False,
                  compiler_invoked=False, simulator_invoked=False, patch_sha256=digest(patch.encode()),
                  inputs={str(root / name): digest(text.encode()) for name, text in originals.items()},
                  helper_pins={str(p): digest(p.read_bytes()) for p in own},
                  after={name: digest(text.encode()) for name, text in candidates.items()})
    for name, text in originals.items():
        if (root / name).read_text() != text:
            raise ValueError('Original Makefile drift during preparation')
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source_root, args.output)
