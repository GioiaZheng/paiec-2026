"""Rebuild the follow-up experiments from pinned tables in a new local workspace.

This is a replication of observed results, not a new prospective validation.
No saved run directories, predictions, credentials or network calls are used.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / 'results/2026-10-31/extensions-reference.json'
SUBMITTED_REVISION = 'd2d3e3c1e803880f4918f2f8065616b513731a40'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_bytes(name):
    if name == 'reproduce_extensions.py':
        # The manifest includes the original driver; keep its recorded hash intact.
        result = subprocess.run(['git', 'show', f'{SUBMITTED_REVISION}:{name}'],
                                cwd=ROOT, capture_output=True)
        if result.returncode:
            raise RuntimeError('The submitted revision is missing. Use a full Git clone.')
        return result.stdout.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
    path = Path(name)
    if path.parent == Path('.') and path.suffix == '.py' and name != 'run_baseline.py':
        path = Path('tests' if name.startswith('test_') else 'experiments') / path
    # Git may check text out with CRLF; recorded source hashes use LF.
    return (ROOT/path).read_text(encoding='utf-8').encode('utf-8')


def recorded_sources(reference):
    sources = {}
    for name, expected in reference['source_sha256'].items():
        content = source_bytes(name)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f'Changed recorded source: {name}')
        sources[name] = content
    return sources


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def compare(actual, expected, location='summary'):
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise AssertionError(f'Changed fields at {location}')
        for key in expected:
            compare(actual[key], expected[key], location + '/' + key)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise AssertionError(f'Changed length at {location}')
        for i, (a, e) in enumerate(zip(actual, expected)):
            compare(a, e, f'{location}/{i}')
    elif isinstance(expected, float):
        if not math.isclose(actual, expected, rel_tol=0., abs_tol=1e-12):
            raise AssertionError(f'Changed value at {location}: {actual} != {expected}')
    elif actual != expected:
        raise AssertionError(f'Changed value at {location}: {actual} != {expected}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT/'data', help='Local pinned formatted tables')
    parser.add_argument('--output', type=Path, help='New, nonexistent workspace directory')
    parser.add_argument('--check-sources', action='store_true', help='Verify frozen sources without running experiments')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Use Python 3.12 for the recorded numerical replication')
    reference = read(REFERENCE)
    if not args.check_sources and args.output is None:
        parser.error('--output is required unless --check-sources is used')
    sources = recorded_sources(reference)
    if args.check_sources:
        print(f'Verified {len(sources)} recorded sources; submitted revision {SUBMITTED_REVISION}')
        return
    destination = args.output.resolve()
    if destination.exists():
        raise FileExistsError('Choose a new output directory; existing runs are never overwritten')
    data_root = args.data.resolve()
    for name, expected in reference['data_sha256'].items():
        relative = Path(name).relative_to('data')
        if sha(data_root/relative) != expected:
            raise ValueError(f'Wrong data revision: {name}')
    destination.mkdir(parents=True)
    for name, content in sources.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for name in reference['data_sha256']:
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(data_root/Path(name).relative_to('data'), target)
    (destination/'local').mkdir()
    (destination/'runs').mkdir()
    logs = destination/'logs'
    logs.mkdir()
    env = dict(os.environ)
    # Only the dependency directory is shared; original source and saved runs are not import paths.
    env['PYTHONPATH'] = str(ROOT/'.deps') if (ROOT/'.deps').is_dir() else ''
    env['PYTHONIOENCODING'] = 'utf-8'
    actions = []
    def run(label, *arguments):
        command = [sys.executable, '-X', 'utf8', *arguments]
        completed = subprocess.run(command, cwd=destination, env=env, capture_output=True, encoding='utf-8')
        (logs/(label+'.txt')).write_text(completed.stdout + completed.stderr, encoding='utf-8')
        actions.append({'step': label, 'arguments': list(arguments), 'exit_code': completed.returncode})
        write(destination/'progress.json', {'status': 'RUNNING', 'actions': actions})
        if completed.returncode:
            raise RuntimeError(f'{label} failed; see {logs/(label+".txt")}\n{completed.stderr[-1800:]}')
        print(label + ': passed', flush=True)
        return completed.stdout
    run('tests', '-m', 'unittest', 'test_evaluation', 'test_diagnostics', 'test_weaker_shrinkage',
        'test_transferred_prior', 'test_adaptive_prior', 'test_retrieval_shrinkage')
    pilots = [
        ('coding-item', None, 'item'), ('coding-near', None, 'near'),
        ('bertaqa-item', 'bertaqa-validation', 'item'), ('bertaqa-source', 'bertaqa-validation', 'source'),
        ('real-item', 'real-validation', 'item'), ('finance-item', 'weaker-shrinkage', 'item'),
        ('truthfulqa-item', 'retrieval-validation', 'item'), ('truthfulqa-near', 'retrieval-validation', 'near'),
    ]
    for label, protocol, split in pilots:
        command = ['evaluate_pilot.py', '--split-unit', split]
        if protocol:
            command += ['--protocol', 'configs/'+protocol+'.json']
        result = json.loads(run(label, *command))
        directory = Path(result['output']).resolve()
        if not directory.is_relative_to(destination/'runs'):
            raise ValueError('Unexpected pilot output path')
        run(label+'-verify', 'verify_pilot.py', str(directory))
        shutil.copytree(directory, destination/'runs'/label)

    transfer = read(destination/'configs/transferred-prior.json')
    transfer['primary_runs'] = ['runs/'+x for x in ('coding-item', 'bertaqa-item', 'real-item', 'finance-item')]
    transfer['sensitivity_runs'] = ['runs/coding-near', 'runs/bertaqa-source']
    write(destination/'configs/transferred-prior.json', transfer)
    for name in ('adaptive-prior', 'retrieval-shrinkage'):
        protocol = read(destination/'configs'/f'{name}.json')
        protocol['parent_run'] = 'runs/prior-transfer'
        write(destination/'configs'/f'{name}.json', protocol)
    source_hashes = {name: sha(destination/name) for name in sources}
    def freeze(name, **extra):
        write(destination/'local'/f'{name}-freeze.json', {
            'status': 'REPLICATION_INPUT_HASHES_NOT_NEW_PREREGISTRATION',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'source_sha256': source_hashes, **extra})
    for name in ('transferred-prior', 'adaptive-prior', 'retrieval-shrinkage'):
        freeze(name)
    run('prior-transfer', 'evaluate_transferred_prior.py')
    parent = Path(read(destination/'local/transferred-prior-output.json')['output'])
    shutil.copytree(parent, destination/'runs/prior-transfer')
    write(destination/'local/optimization-review-2026-10-31.json', {
        'status': 'REPLICATION_PARENT_EVIDENCE',
        'evidence_sha256': {n: sha(parent/n) for n in ('summary.json','pairs.json','protocol.json','lexical_audit.json')}})
    run('adaptive-mixture', 'evaluate_adaptive_prior.py')
    run('lexical-development', 'evaluate_retrieval_shrinkage.py')
    run('lexical-development-verify', 'verify_retrieval.py')

    # Recompute the metadata-only overlap audit; this repeat is not label-naive prospective evidence.
    sys.path.insert(0, str(ROOT/'.deps'))
    sys.path.insert(0, str(destination))
    import pyarrow.parquet as pq
    from near_duplicates import audit_items
    texts = {}
    for benchmark in [*transfer['benchmarks'], 'truthfulqa_mc']:
        for row in pq.read_table(destination/'data'/benchmark/'items.parquet').to_pylist():
            text, key = row['content'], row['item_id']
            if benchmark == 'bertaqa':
                messages = json.loads(text)
                text = [m['content'] for m in messages if m.get('role') == 'user'][-1]
                key = row['raw_item_id']
            name = benchmark+'/'+key
            if name in texts and texts[name] != text:
                raise ValueError('Conflicting canonical question text')
            texts[name] = text
    _, audit = audit_items(texts)
    crossing = [p for p in audit['pairs'] if p['left'].split('/')[0] != p['right'].split('/')[0]]
    within = [p for p in audit['pairs'] if p['left'].startswith('truthfulqa_mc/') and p['right'].startswith('truthfulqa_mc/')]
    if crossing or within:
        raise ValueError('Reproduced lexical audit found unresolved overlap')
    audit_path = destination/'local/truthfulqa-label-blind-audit.json'
    write(audit_path, {'status': 'REPLICATION_OF_METADATA_ONLY_AUDIT',
                      'cross_benchmark_matches': crossing, 'within_benchmark_matches': within,
                      'scope': audit['scope']})
    freeze('retrieval-validation', metadata_audit_sha256=sha(audit_path))
    run('lexical-validation', 'validate_retrieval.py', 'runs/truthfulqa-item', 'runs/truthfulqa-near')
    run('lexical-validation-verify', 'verify_retrieval_validation.py')

    experiments = {}
    for method, pointer in [('transfer', 'transferred-prior'), ('adaptive', 'adaptive-prior'),
                            ('retrieval', 'retrieval-shrinkage'), ('validation', 'retrieval-validation')]:
        folder = Path(read(destination/'local'/f'{pointer}-output.json')['output'])
        summary = read(folder/'summary.json')
        expected = reference['experiments'][method]
        compare(summary['summaries'], expected['summaries'], method)
        flag = 'validation_passed' if method == 'validation' else 'screen_passed'
        compare(summary[flag], expected[flag], method+'/'+flag)
        if method in ('retrieval', 'validation'):
            check = read(folder/'independent_verification.json')
            assert check['status'] == 'PASS' and check['summary_sha256'] == sha(folder/'summary.json')
        experiments[method] = {'run': folder.relative_to(destination).as_posix(),
                               'summary_sha256': sha(folder/'summary.json'), flag: summary[flag],
                               'recorded_aggregates_match': True}
    result = {'status': 'PASS', 'scope': 'Numerical replication of existing public-data experiments; no new validation evidence',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'reused_saved_runs': False,
              'downloaded_data': False, 'uploaded': False, 'absolute_tolerance': 1e-12,
              'reference_sha256': sha(REFERENCE), 'driver_sha256': sha(Path(__file__)),
              'data_sha256': reference['data_sha256'], 'source_sha256': source_hashes,
              'actions': actions, 'experiments': experiments}
    write(destination/'replication.json', result)
    write(destination/'progress.json', {'status': 'PASS', 'actions': actions})
    print(json.dumps({'status': 'PASS', 'output': str(destination), 'experiments': experiments}, indent=2))


if __name__ == '__main__':
    main()
