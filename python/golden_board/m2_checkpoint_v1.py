"""Preserve the completed M2 result; never produce a result for live source."""
from hashlib import sha256
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from . import canonical_manifest as manifest
from .m2_gate8 import _real_repository
from .m2_gate8_policy_v2 import load_gate8_policy_v2
from .m2_source_v2 import read_source_file_v2, validate_source_projection_v2

PATH = 'studies/m2/checkpoint-v1.json'
LEGACY_INPUT_PREFIXES = ('artifacts/linux/',
                         'artifacts/history/m2-r1-candidates/owners/',
                         'artifacts/history/m2-r2-candidates/owners/')
PINS = dict(
    schema='golden-board.m2-completed-checkpoint/v1',
    source_commit='5d9254d2f6b755013d7d0b86ea7e935e8ee08257',
    source_projection_sha256='60fe31a75ffe5f2d4e71558a7d13356f0db90e9ff7d45a74386cd26c10bb7b65',
    report_sha256='4a92d662882294a67e6ca6d44e31e401a7d2cd53f1428e81f7e4335cb7808aa0',
    qualification_sha256='479476b85cee58c79db83998a98e8cb5480fbd329359722b26c119eb4bece46e',
    candidate_manifest_sha256='83c8ea8c3cad907d6fcef3b8b5a4b2b3403017c8744e786c8808c1b53bc999a0',
    transition_manifest_sha256='6c9c4e7a70bd8d281425885416aef77c237fdf827a547300b6dc5c7eb5928d25',
    verifier_acquisition_sha256='315f9021f83ee8c6640af6ea6bcd58387287bcef42e7b27eaaf5f76b2187f6a2')


def require(ok, reason):
    if not ok:
        raise ValueError('m2-checkpoint-v1:' + reason)


def _git(root, *arguments):
    environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    environment.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_OPTIONAL_LOCKS='0')
    # Git diagnostics go to bounded-time private files, never an unbounded pipe.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c',
                                 'core.fsmonitor=false', '-C', str(root), *arguments],
                                env=environment, stdout=output, stderr=errors, timeout=30)
        require(result.returncode == 0, 'local-Git-preimage-missing')
        require(output.tell() <= 1048576 and errors.tell() <= 65536, 'git-output-bound')
        output.seek(0)
        return output.read(1048576)


def _descriptor(root):
    root = _real_repository(root)
    raw = read_source_file_v2(root, PATH, 8192)[0]
    require(manifest.validate_canonical_manifest(raw) == PINS, 'descriptor-binding')
    return root


def _clone_source(root, destination):
    require(destination.is_absolute() and destination == destination.resolve()
            and not os.path.lexists(destination), 'fresh-absolute-destination')
    require(destination.parent.is_dir() and not destination.parent.is_symlink(), 'destination-parent')
    _git(root, 'clone', '--local', '--no-hardlinks', '--no-checkout', str(root), str(destination))
    _git(destination, 'checkout', '--detach', PINS['source_commit'])
    require(_git(destination, 'rev-parse', 'HEAD').strip().decode() == PINS['source_commit'], 'source-commit')
    return _real_repository(destination)


def _evidence(root, frozen):
    """Rehash the original complete closure; original gate algorithms stay intact."""
    from tools.m2 import generate_gate8_v2 as producer
    from tools.m2 import reopen_participant_revision as transition
    from .m2_gate8_evidence_v2 import gate8_paths_v2, validate_generated_evidence_v2
    from .m2_gate8_receipts_v2 import (admit_producer_receipt_v2,
                                    validate_cross_language_v2, admit_linux_attestation_v2)
    from .m2_qualification_v2 import admit_qualification_v2, recover_ready_roadmap_v2
    from .m2_gate8_reports_v2 import recover_pending_roadmap_v2

    policy = load_gate8_policy_v2(read_source_file_v2(frozen, 'spec/gate8-policy-v2.toml')[0])
    owner = policy.document
    candidate = owner['authority']['candidate_root']
    gate8 = owner['authority']['gate8_root']
    def read(path):
        try:
            raw = read_source_file_v2(root, path, 4194306)[0]
            require(stat.S_IMODE((root / path).lstat().st_mode) == 0o644,
                    'preimage-mode:' + path)
            return raw
        except (OSError, ValueError) as error:
            raise ValueError('m2-checkpoint-v1:required-preimage:' + path) from error
    pins = {'source_projection_sha256': owner['source_projection']['path'],
            'report_sha256': owner['authority']['report_path'],
            'qualification_sha256': 'studies/m2/qualification-v2.json',
            'candidate_manifest_sha256': candidate + '/candidate-manifest.json',
            'verifier_acquisition_sha256': 'artifacts/linux/verifier-v0.env'}
    for key, path in pins.items():
        require(sha256(read(path)).hexdigest() == PINS[key], 'preimage:' + path)
    source = read(owner['source_projection']['path'])
    validate_source_projection_v2(source, frozen, policy)
    try:
        archive = transition._load_package(root / transition.ARCHIVE, PINS['transition_manifest_sha256'])
    except transition.TransitionError as error:
        raise ValueError('m2-checkpoint-v1:required-transition-archive:' + str(error)) from error
    candidate_rows = producer.tree_rows(root / candidate, 4120, 1048576, 570425344)
    gate_rows = producer.tree_rows(root / gate8, 272, 4194306, 83886080)
    gate_names = tuple(gate8 + '/' + row['path'] for row in gate_rows)
    require(gate_names == gate8_paths_v2(policy), 'gate8-inventory')
    generated_path = owner['generated_evidence']['path']
    report = manifest.validate_canonical_manifest(read(owner['authority']['report_path']))
    bindings = {row['name']: row['sha256'] for row in report['generated_evidence_hashes']}
    require(sha256(read(generated_path)).hexdigest() == bindings[generated_path], 'generated-binding')
    generated = manifest.validate_canonical_manifest(read(generated_path))
    require(generated['candidate_file_rows'] == [dict(row, path=candidate + '/' + row['path'])
                                                for row in candidate_rows], 'candidate-preimages')
    damage_paths = tuple(row['path'] for row in candidate_rows
                         if row['path'] == 'resource-limits.json' or row['path'].startswith('damage/'))
    validate_generated_evidence_v2(read(generated_path), policy, source, damage_paths,
        lambda p: read(candidate + '/' + p), read,
        candidate_names=tuple(row['path'] for row in candidate_rows),
        gate8_names=tuple(p for p in gate_names if p != generated_path))
    def source_read(path):
        return read(path) if path == 'artifacts/linux/verifier-v0.env' else read_source_file_v2(frozen, path)[0]
    receipts = {}
    for name in owner['producer_receipt']['producer_order']:
        raw = read(owner['producer_receipt']['path'].format(producer_id=name))
        value = admit_producer_receipt_v2(raw, policy, source, damage_paths, source_read=source_read)
        require(value['producer_id'] == name and value['file_rows'] == list(candidate_rows), 'receipt-preimages')
        receipts[name] = raw
    validate_cross_language_v2(read(owner['cross_language']['path']), policy, source,
                              receipts, damage_paths, source_read=source_read)
    admit_linux_attestation_v2(read(owner['linux']['attestation_path']), policy, source, receipts,
                              damage_paths, read('artifacts/linux/verifier-v0.env'), source_read=source_read)
    qualification_raw = read('studies/m2/qualification-v2.json')
    qualification = admit_qualification_v2(qualification_raw, policy, root)
    trial = 'artifacts/quiz/20-open-technical-group/'
    preimages = {'answers/group-final/answer.md': qualification['technical']['group_final_sha256'],
                'owner/human-review.md': qualification['technical']['review_sha256'],
                'learner-answers/answer.md': qualification['learner']['answer_sha256'],
                'learner-answers/learner-attempt-1.json': qualification['learner']['attempt_sha256'],
                'owner/learner-review.json': qualification['learner']['review_sha256'],
                'owner/source-snapshot.json': qualification['frozen_source_snapshot_sha256']}
    for path, expected in preimages.items():
        require(sha256(read(trial + path)).hexdigest() == expected, 'qualification-preimage:' + path)
    roadmap = read_source_file_v2(frozen, 'docs/roadmap.md')[0]
    ready = recover_ready_roadmap_v2(policy, roadmap, read(owner['authority']['report_path']), qualification_raw)
    recover_pending_roadmap_v2(policy, ready, read(owner['authority']['report_path']))
    files = [candidate + '/' + row['path'] for row in candidate_rows] + list(gate_names)
    files += ['artifacts/linux/verifier-v0.env'] + [trial + p for p in preimages]
    files += [transition.ARCHIVE + '/archive-manifest.json']
    files += [transition.ARCHIVE + '/' + row['archive_path'] for key in ('files', 'pending') for row in archive[key]]
    return sorted(set(files)), archive


def admit_completed_m2_checkpoint_v1(root: Path) -> dict:
    """Read-only historical integrity, independent of current development status."""
    root = _descriptor(root)
    with tempfile.TemporaryDirectory(prefix='gb-m2-frozen-source-') as temp:
        frozen = _clone_source(root, Path(temp).resolve() / 'source')
        _evidence(root, frozen)
    return dict(PINS)


def materialize_completed_m2_checkpoint_v1(root: Path, destination: Path) -> Path:
    """Restore exact local source/evidence into a fresh ordinary Git repository."""
    root = _descriptor(root)
    destination = Path(destination)
    frozen = _clone_source(root, destination)
    try:
        files, archive = _evidence(root, frozen)
        from tools.m2 import reopen_participant_revision as transition
        for name in archive['directories']:
            directory = frozen / transition.ARCHIVE / 'prior' / name
            directory.mkdir(parents=True, exist_ok=True)
            for parent in (directory, *directory.parents):
                if parent == frozen:
                    break
                if parent.is_relative_to(frozen / 'artifacts'):
                    parent.chmod(0o700)
        for path in files:
            source = root / path
            target = frozen / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
            # Every archived directory is private; ordinary generated directories
            # are private too. File modes remain their admitted original modes.
            for parent in target.parents:
                if parent == frozen:
                    break
                if parent.is_relative_to(frozen / 'artifacts'):
                    parent.chmod(0o700)
        # Frozen component tests still read these ignored historical inputs.
        # Restore from the admitted transition tuple, never a mutable live copy.
        for name in archive['directories']:
            if name.startswith(LEGACY_INPUT_PREFIXES):
                directory = frozen / name
                directory.mkdir(parents=True, exist_ok=True)
                for parent in (directory, *directory.parents):
                    if parent == frozen:
                        break
                    if parent.is_relative_to(frozen / 'artifacts'):
                        parent.chmod(0o700)
        for row in archive['files']:
            if row['path'].startswith(LEGACY_INPUT_PREFIXES):
                source = root / transition.ARCHIVE / row['archive_path']
                target = frozen / row['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)
                target.chmod(int(row['mode'], 8))
                require(target.stat().st_size == row['byte_length']
                        and sha256(target.read_bytes()).hexdigest() == row['sha256'],
                        'restored-legacy-preimage:' + row['path'])
        _evidence(frozen, frozen)
        return frozen
    except BaseException:
        shutil.rmtree(frozen)
        raise
