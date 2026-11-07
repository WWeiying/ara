"""Exact, reversible controller/VLSU build-input transforms; no file writes.

Identity reference: accepted physical_wide_soc_inputs_20261106_01/source.
The caller owns the fresh build tree, complete filelist and execution gates.
"""
import hashlib
from pathlib import Path


SOURCE_ROOT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/'
                   'e2e_physical_wide_soc_inputs_20261106_01/source')
ENGINE_SOURCE = SOURCE_ROOT / 'hardware/src/vlsu/qbs/qbs_engine.sv'
VLSU_SOURCE = SOURCE_ROOT / 'hardware/src/vlsu/vlsu.sv'
ENGINE_SHA = '0814e549e5c8e0c4bb8eaf2dae816b133d04d3d57648245cb496e7599c8531f4'
VLSU_SHA = '847fb761566f3fab4a3f0310f512f73e644ad386db3d6c2ae11bdf456d6ed40d'
EXPERIMENT_DEFINE = 'ARA_EXPERIMENT_BALANCED_MATRIX_DOT'
MACRO_GUARD = '''`ifndef ARA_EXPERIMENT_BALANCED_MATRIX_DOT
`define ARA_EXPERIMENT_BALANCED_MATRIX_DOT 0
`endif

'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def _transform(source, expected, identity_path, replacements):
    require(isinstance(source, str) and sha(source) == expected,
            'Exact accepted snapshot SHA required: ' + str(identity_path))
    text, edits = source, []
    for label, before, after in replacements:
        require(text.count(before) == 1, 'Exact unique anchor required: ' + label)
        text = text.replace(before, after, 1)
        edits.append(dict(label=label, before=before, after=after, count=1))
    restored = text
    for edit in reversed(edits):
        require(restored.count(edit['after']) == 1, 'Ambiguous inverse anchor: ' + edit['label'])
        restored = restored.replace(edit['after'], edit['before'], 1)
    require(restored == source, 'Original source did not restore exactly')
    return text, dict(identity_reference_path=str(identity_path), original_sha256=expected,
                      generated_sha256=sha(text), edits=edits, source_reversible=True,
                      default_disabled=True, target_executed=False, rtl_compiled=False,
                      hierarchy_preserved=True, original_port_connections_unchanged=True,
                      limits=['Isolated source preparation only; not full-controller or SoC acceptance',
                              'Complete controller, seed/abort and balanced-M4 handoff gates remain required'])


def engine(source):
    """Return (qbs_engine_balanced text, report), accepting only ENGINE_SHA."""
    old_compute = '''  qbs_compute_engine #(
    .SeedRestoreEnable(SeedRestoreEnable), .WideMatrixDot(WideMatrixDot),
    .WideWeightIngress(WideWeightIngress)
  ) i_compute_engine ('''
    new_compute = '''  qbs_compute_engine_balanced #(
    .SeedRestoreEnable(SeedRestoreEnable), .WideMatrixDot(WideMatrixDot),
    .WideWeightIngress(WideWeightIngress), .BalancedMatrixDot(BalancedMatrixDot)
  ) i_compute_engine ('''
    guard = '''`ifndef SYNTHESIS
  initial begin
    assert (!BalancedMatrixDot || WideMatrixDot)
      else $fatal(1, "BalancedMatrixDot requires WideMatrixDot");
  end
`endif

'''
    text, report = _transform(source, ENGINE_SHA, ENGINE_SOURCE, [
        ('module-name', 'module qbs_engine\n', 'module qbs_engine_balanced\n'),
        ('optional-parameter', "    parameter bit WideMatrixDot = 1'b0,",
         "    parameter bit WideMatrixDot = 1'b0,\n    parameter bit BalancedMatrixDot = 1'b0,"),
        ('balanced-compute-instance', old_compute, new_compute),
        ('parameter-contract', 'endmodule : qbs_engine', guard + 'endmodule : qbs_engine'),
        ('endmodule-name', 'endmodule : qbs_engine', 'endmodule : qbs_engine_balanced'),
    ])
    report.update(original_module='qbs_engine', generated_module='qbs_engine_balanced',
                  parameter='BalancedMatrixDot', requires='BalancedMatrixDot implies WideMatrixDot',
                  compute_module='qbs_compute_engine_balanced', compute_instance='i_compute_engine',
                  seed_restore_passthrough_unchanged=True, seed_mapper_unchanged=True,
                  reader_context_commit_and_fault_logic_unchanged=True,
                  requires_balanced_compute_clone=True)
    return text, report


def vlsu(source):
    """Return (override vlsu text, report), accepting only VLSU_SHA.

    The VLSU module/instance hierarchy is not renamed. An absent experimental
    define becomes numeric zero; an existing definition is never overwritten.
    Enable only in the fresh filelist with +define+ARA_EXPERIMENT_BALANCED_MATRIX_DOT=1.
    """
    module = 'module vlsu import ara_pkg::*; import rvv_pkg::*; import qbs_pkg::*;'
    old_engine = '''  qbs_engine #(
    .reader_req_t(shared_read_req_t), .reader_rsp_t(shared_read_rsp_t),
    .WideWeightIngress(QbsWideWeightIngressEnable),'''
    new_engine = '''  qbs_engine_balanced #(
    .reader_req_t(shared_read_req_t), .reader_rsp_t(shared_read_rsp_t),
    .WideWeightIngress(QbsWideWeightIngressEnable),
    .BalancedMatrixDot(`ARA_EXPERIMENT_BALANCED_MATRIX_DOT),'''
    text, report = _transform(source, VLSU_SHA, VLSU_SOURCE, [
        ('default-off-experimental-define', module, MACRO_GUARD + module),
        ('balanced-engine-instance', old_engine, new_engine),
    ])
    report.update(original_module='vlsu', generated_module='vlsu',
                  engine_module='qbs_engine_balanced', engine_instance='i_qbs_engine',
                  experimental_define=EXPERIMENT_DEFINE, undefined_macro_default=0,
                  existing_macro_definition_preserved=True,
                  enable_flag='+define+' + EXPERIMENT_DEFINE + '=1',
                  seed_restore_and_command_seed_connections_unchanged=True,
                  clock_reader_akv_commit_and_probe_connections_unchanged=True,
                  production_filelist_or_macros_modified=False)
    return text, report
