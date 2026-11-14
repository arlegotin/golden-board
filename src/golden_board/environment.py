"""Normal pip setup from retained, publisher-checked dependency archives."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import venv


def verify_dependencies(root: Path, acquire: bool = False) -> list[dict]:
    directory = root / 'inputs/dependencies'
    lock = json.loads((directory / 'lock.json').read_text())
    for item in lock['files']:
        path = directory / item['filename']
        if not path.is_file():
            if not acquire:
                raise ValueError(f'Missing {path}. Restore the locked archive from the original input bundle, then run ./gb setup --offline.')
            try:
                with urllib.request.urlopen(item['url'], timeout=60) as response:
                    data = response.read()
            except (OSError, urllib.error.URLError) as error:
                raise ValueError(f'Cannot acquire {item["url"]}: {error}. '
                                 'Restore the locked archive before offline setup, or explicitly call the acquisition API.') from error
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError(f'{path}: downloaded hash mismatch; no package installed.')
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
                stream.write(data)
                temporary = Path(stream.name)
            temporary.replace(path)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != item['sha256'] or len(data) != item['bytes']:
            raise ValueError(f'{path}: hash mismatch; retain/quarantine the changed file '
                             'and restore the locked archive. No automatic replacement.')
    return lock['files']


def _run(command: list[str], root: Path, log) -> str:
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    log.write(json.dumps({'command': command, 'exit': result.returncode,
                          'stdout': result.stdout, 'stderr': result.stderr}) + '\n')
    log.flush()
    if result.returncode:
        raise ValueError(f'Command failed ({result.returncode}): {command}\n'
                         f'{result.stdout[-3000:]}\n{result.stderr[-3000:]}')
    return result.stdout.strip()


def setup(root: Path, acquire: bool, destination: Path | None = None) -> dict:
    root = root.resolve()
    if sys.version_info[:2] != (3, 14):
        raise ValueError('Supported runtime is Python 3.14; run gb using python3.14.')
    packages = verify_dependencies(root, acquire)
    destination = (destination or root / '.venv').resolve()
    logs = root / 'build/setup'
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=logs, suffix='.jsonl',
                                     prefix='setup-', delete=False) as log:
        if not (destination / 'pyvenv.cfg').is_file():
            venv.EnvBuilder(with_pip=True).create(destination)
        python = str(destination / 'bin/python')
        pip = [python, '-I', '-m', 'pip', '--isolated', 'install',
               '--disable-pip-version-check', '--no-index', '--no-deps',
               '--no-build-isolation', '--no-cache-dir', '--require-hashes',
               '--find-links', str(root / 'inputs/dependencies')]
        for requirements in ('requirements-build.lock', 'requirements.lock'):
            _run(pip + ['-r', str(root / requirements)], root, log)
        version = _run([python, '-I', '-c', 'import chess; print(chess.__version__)'], root, log)
        if version != '1.11.2':
            raise ValueError(f'Installed chess version {version}; expected 1.11.2.')
        report = {'python': _run([python, '--version'], root, log), 'chess': version,
                  'platform': platform.platform(), 'venv': str(destination),
                  'dependency_sha256': {item['filename']: item['sha256'] for item in packages},
                  'log': str(Path(log.name).relative_to(root))}
    return report


def reference_smoke(root: Path) -> dict:
    """Narrow package/API smoke, not independent all-source qualification."""
    verify_dependencies(root)
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / 'chess.cjs'
        with tarfile.open(root / 'inputs/dependencies/chess.js-1.4.0.tgz') as archive:
            target.write_bytes(archive.extractfile('package/dist/cjs/chess.js').read())
        version = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
        if not version.stdout.startswith('v22.'):
            raise ValueError(f'Supported reference runtime is Node 22; observed {version.stdout.strip()}.')
        result = subprocess.run(['node', '-e',
            "const {Chess}=require(process.argv[1]); const game=new Chess(); "
            "if(game.moves().length!==20) throw Error('initial legal count'); "
            "game.move('e4',{strict:true}); console.log(JSON.stringify({e4_fen:game.fen()}));",
            str(target)], capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    expected = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
    if report['e4_fen'] != expected:
        raise ValueError(f'chess.js e4 smoke mismatch: {report["e4_fen"]}')
    report['node'] = version.stdout.strip()
    report['scope'] = 'independent package smoke only; full source replay pending S4'
    return report
