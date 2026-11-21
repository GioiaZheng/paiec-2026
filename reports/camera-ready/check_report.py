"""Check this draft and its immutable originals; write a local preflight record."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path)
    args = parser.parse_args()
    reader = PdfReader(HERE/'paiec_report.pdf')
    pages = [p.extract_text() for p in reader.pages]
    assert len(pages) == 13
    # The archive ships the checked PDF, not local .aux/.log files.
    aux = HERE/'paiec_report.aux'
    if aux.exists():
        assert re.search(r'\\newlabel\{main-end\}\{\{[^}]*\}\{7\}', aux.read_text())
    assert 'References' in pages[7] and 'Reproduction outline' in pages[8]
    assert 'Post-review diagnostics' in pages[10] and 'Calibration at' in pages[12]
    log = HERE/'paiec_report.log'
    if log.exists():
        assert not re.search(r'Overfull|Underfull|Warning|undefined|LaTeX Error', log.read_text())
    text = '\n'.join(pages)
    assert '??' not in text and 'Development disclosure' in text
    assert 'Workshop: Predictive AI Evaluation' in pages[0]
    assert '84%' in pages[0] and 'two coding benchmarks' in pages[0]
    assert all(v in text for v in ['0.25527', '0.21963', '0.003215', '0.000005', '6,012', '992850'])
    submitted = (HERE/'source/submitted_report.tex').read_text()
    revised = (HERE/'paiec_report.tex').read_text()
    tables = lambda s: re.findall(r'\\begin\{table\}.*?\\end\{table\}', s, re.S)
    orig_tables, new_tables = tables(submitted), tables(revised)
    assert len(orig_tables) == 5 and len(new_tables) == 8
    for i, t in enumerate(orig_tables):
        if i == 1:
            t = t.replace('Population & Mean ALC', r'Population & \shortstack{Empirical-mean\\ALC}')
        assert t == new_tables[i], f'Original table {i+1} changed'
    template = json.loads((HERE/'template-manifest.json').read_text())
    assert sha(HERE/'neurips_2026.sty') == template['style_sha256']
    assert b'\r' not in (HERE/'analysis/inputs.json').read_bytes()
    assert b'\r' not in (HERE/'analysis/results.json').read_bytes()
    release_url = 'https://github.com/GioiaZheng/paiec-2026/releases/download/camera-ready-2026-11-21/paiec-camera-ready-source.zip'
    links = {str(a.get_object().get('/A', {}).get('/URI', '')) for p in reader.pages for a in p.get('/Annots', [])}
    assert release_url in links
    # Recompute statistics once from the shipped inputs and require identical output.
    result_before = sha(HERE/'analysis/results.json')
    test = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'analysis', '-p', 'test_analysis.py', '-v'], cwd=HERE, text=True, capture_output=True)
    assert test.returncode == 0, test.stdout+test.stderr
    run = subprocess.run([sys.executable, 'analysis/analyze.py'], cwd=HERE, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert result_before == sha(HERE/'analysis/results.json')
    fonts = {}

    def audit(resources):
        if not resources:
            return
        resources = resources.get_object()
        for f in resources.get('/Font', {}).values():
            f = f.get_object()
            desc = f.get('/FontDescriptor')
            if f.get('/Subtype') == '/Type0':
                desc = f['/DescendantFonts'][0].get_object().get('/FontDescriptor')
            desc = desc.get_object() if desc else {}
            embedded = any(k in desc for k in ('/FontFile','/FontFile2','/FontFile3'))
            fonts[str(f.get('/BaseFont'))] = embedded
        for obj in resources.get('/XObject', {}).values():
            audit(obj.get_object().get('/Resources'))
    for p in reader.pages:
        audit(p.get('/Resources'))
    assert all(fonts.values()), fonts
    frozen = {}
    expected = {
        'local/submission/paiec_report.pdf': 'f139f762a922cfd5612965217d73d36ee627984a50d7fe3be9803ca774c5d17f',
        'local/submission/paiec_report.tex': '6cbb19e654abae43a274b5930e6f86213df731ccebada926bbc576d3f08e842e',
        'local/submission/paiec-supplementary.zip': '3a2ac071be3af99591ae671dbf7152b1e9ea5196eadc8864f9dd3793ac11d3dc',
        'dist/shrinkage.zip': '881e3bb205fd02a4d6657549b102e44501322d6868c0e0bcdb2f4f1141e1d9a0'}
    if args.project:
        for p, digest in expected.items():
            assert sha(args.project/p) == digest, p
            frozen[p] = digest
    result = {'status': 'LOCAL_CAMERA_READY_DRAFT_CHECKED_NOT_UPLOADED', 'checked_on': '2026-11-21',
              'pages': len(pages), 'main_pages': 7, 'original_table_values_unchanged': True,
              'tests': 5, 'test_output': test.stderr.strip(), 'statistics_recomputed_identically': True,
              'fonts_embedded': fonts, 'latex_log_checked': log.exists(),
              'latex_warnings': [] if log.exists() else None, 'json_newline': 'LF',
              'diagnostic_bundle_url': release_url, 'frozen_originals': frozen,
              'artifacts': {p: {'sha256': sha(HERE/p), 'bytes': (HERE/p).stat().st_size} for p in ['paiec_report.pdf', 'paiec_report.tex', 'analysis/inputs.json', 'analysis/results.json']},
              'limits': ['No OpenReview upload established by this check',
                         'Release URL is checked structurally here, not for remote availability',
                         'No hosted evaluation or new prospective validation']}
    (HERE/'preflight.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({k:result[k] for k in ['status','pages','main_pages','tests','statistics_recomputed_identically']}))


if __name__ == '__main__':
    main()
