"""Package only the reviewed manuscript source and group-level diagnostics."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
FILES = ['README.md', 'LICENSE', 'requirements-tools.txt', 'paiec_report.pdf',
         'paiec_report.tex', 'build_report.py', 'plot_calibration.py', 'check_report.py',
         'package_source.py', 'neurips_2026.sty', 'environ.sty', 'trimspaces.sty',
         'template-manifest.json', 'source/submitted_report.tex', 'figures/reliability.pdf',
         'analysis/config.json', 'analysis/inputs.json', 'analysis/results.json',
         'analysis/collect_inputs.py', 'analysis/analyze.py', 'analysis/test_analysis.py']


def main():
    records = [{'path': p, 'bytes': (HERE/p).stat().st_size,
                'sha256': hashlib.sha256((HERE/p).read_bytes()).hexdigest()} for p in FILES]
    manifest = {'status': 'CAMERA_READY_DIAGNOSTIC_BUNDLE',
                'prepared_on': '2026-11-21', 'files': records,
                'original_code_revision': 'd2d3e3c1e803880f4918f2f8065616b513731a40',
                'codabench_submission': '992850',
                'notes': 'New report source bundle; not a CodaBench archive or replacement of the original supplementary ZIP.'}
    (HERE/'source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    archive = HERE/'paiec-camera-ready-source.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in FILES+['source-manifest.json']:
            info = zipfile.ZipInfo(p, date_time=(2026,11,21,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, (HERE/p).read_bytes())
    with zipfile.ZipFile(archive) as z:
        assert not z.testzip()
        for r in records:
            assert hashlib.sha256(z.read(r['path'])).hexdigest() == r['sha256']
    print(json.dumps({'files': len(FILES)+1, 'bytes': archive.stat().st_size,
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
