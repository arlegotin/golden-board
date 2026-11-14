"""Offline construction, verification and headless inspection of the final message."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FAST = ['document', 'self_contained_format', 'direct_stream', 'clean_content', 'artifacts', 'cli', 'bootstrap_boundaries', 'guide_images']
CONTENT = ['clean_content', 'practical_course', 'advanced_state', 'advanced_course',
           'teaching_boundaries', 'history_segments', 'move_packing', 'anthology_schema', 'piece_glyphs']
AREAS = {'source': ['source', 'anthology'], 'rules': ['rules'],
         'content': CONTENT, 'carrier': ['bootstrap_clarity', 'bootstrap_boundaries', 'direct_stream', 'guide_images'],
         'player': ['document'], 'artifacts': ['artifacts']}
JS = ['tests/'+name+'.test.mjs' for name in ('player','passive','catalog','catalog-relay')]


def _check(args):
    from .source import verify_source
    from .environment import verify_dependencies, reference_smoke
    if (args.scope == 'focused') != (args.area is not None):
        raise ValueError('Use check focused AREA, check fast, or check integration.')
    source = verify_source(ROOT)
    verify_dependencies(ROOT)
    names = (AREAS[args.area] if args.scope == 'focused' else FAST if args.scope == 'fast'
             else sorted(p.stem.removeprefix('test_') for p in (ROOT/'tests').glob('test_*.py')))
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName('tests.test_'+name) for name in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'scope': args.scope, 'area': args.area, 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'source_sha256': source['sha256'], 'result': 'passed' if result.wasSuccessful() else 'failed'}
    if result.wasSuccessful() and (args.scope != 'focused' or args.area == 'player'):
        run = subprocess.run(['node', '--test', *JS], cwd=ROOT, capture_output=True, text=True)
        report['javascript'] = {'exit': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
        if run.returncode: report['result'] = 'failed'
    if result.wasSuccessful() and args.area == 'source':
        from .anthology import qualify_anthology
        from .anthology_playback import measure_anthology
        qualified = qualify_anthology(ROOT)
        report['source_qualification'] = qualified
        if not qualified['qualified']:
            report['result'] = 'failed'
        else:
            report['anthology_playback'] = measure_anthology(ROOT, qualified)
            if not report['anthology_playback']['passed']: report['result'] = 'failed'
    if args.scope == 'integration' and report['result'] == 'passed':
        report['reference_package_smoke'] = reference_smoke(ROOT)
    report['qualification_scope'] = 'Current automated regression only; historical recipient evidence is not rerun.'
    (ROOT/'build/checks').mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=ROOT/'build/checks', prefix='check-', suffix='.json', delete=False) as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
        path = str(Path(stream.name).relative_to(ROOT))
    return report['result'] == 'passed', {'result': report['result'], 'tests': result.testsRun, 'report': path,
                                         'javascript_exit': report.get('javascript',{}).get('exit')}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='./gb', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    setup_parser = commands.add_parser('setup', help='Install locked packages from retained archives')
    setup_parser.add_argument('--offline', action='store_true', required=True)
    verify = commands.add_parser('verify', help='Check all canonical representations and content')
    verify.add_argument('--transforms', action='store_true')
    inspect = commands.add_parser('inspect', help='List or extract checked canonical documents')
    inspect.add_argument('--output', type=Path)
    check = commands.add_parser('check', help='Run current regression and independent checks')
    check.add_argument('scope', choices=['fast', 'focused', 'integration'])
    check.add_argument('area', nargs='?', choices=list(AREAS))
    for name in ('build', 'reproduce'):
        command = commands.add_parser(name, help='Build into a fresh directory'+(' and compare frozen outputs' if name == 'reproduce' else ''))
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # A clean source export starts with no generated directories.
        (ROOT/'build').mkdir(exist_ok=True)
        if args.command == 'setup':
            from .environment import setup
            from .source import verify_source
            source = verify_source(ROOT)
            report = setup(ROOT, acquire=False)
            report['source_sha256'] = source['sha256']
        elif args.command == 'verify':
            from .artifacts import verify_artifacts
            report = verify_artifacts(ROOT, args.transforms)
        elif args.command == 'inspect':
            from .artifacts import verify_artifacts, sha
            from .clean_carrier import decode_serial
            from .document import decode_document
            verify_artifacts(ROOT)
            bodies = decode_serial((ROOT/'artifacts/GOLDEN-BOARD.txt').read_bytes())['documents']
            report = {'scope': 'Native checked extraction, not recipient discovery', 'documents': {}}
            for ident, body in bodies.items():
                model = decode_document(body)
                report['documents'][str(ident)] = {'bytes': len(body), 'sha256': sha(body),
                    'entries': model['entries'], 'records': len(model['records'])}
            if args.output is not None:
                destination = args.output.resolve()
                destination.mkdir(parents=True, exist_ok=False)
                for ident, body in bodies.items(): (destination/f'{ident}.bin').write_bytes(body)
                (destination/'inventory.json').write_text(json.dumps(report, indent=2)+'\n')
        elif args.command in ('build','reproduce'):
            from .clean_build import build_clean
            from .artifacts import verify_artifacts, png_packed
            report = build_clean(ROOT, args.output)
            report = {'output': str(args.output.resolve()), 'artifact_sha256': report['artifact_sha256'],
                      'scope': report['scope'], 'release_ready': False}
            if args.command == 'reproduce':
                verify_artifacts(ROOT)
                for generated, canonical in (('GOLDEN-BOARD.bitplane','GOLDEN-BOARD.bin'),
                                              ('serial.txt','GOLDEN-BOARD.txt'),('GOLDEN-BOARD.png','GOLDEN-BOARD.png')):
                    if (args.output/generated).read_bytes() != (ROOT/'artifacts'/canonical).read_bytes():
                        raise ValueError('Reproduction byte mismatch: '+generated)
                expected = json.loads((ROOT/'artifacts/manifest.json').read_bytes())['documents']
                for ident, row in expected.items():
                    if hashlib.sha256((args.output/f'documents/{ident}.bin').read_bytes()).hexdigest() != row['sha256']:
                        raise ValueError('Reproduction document mismatch: '+ident)
                report['exact'] = True
                (args.output/'REPRODUCED.json').write_text(json.dumps(report,indent=2)+'\n')
        else:
            passed, report = _check(args)
            print(json.dumps(report,indent=2)); return 0 if passed else 1
        print(json.dumps(report,indent=2))
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
