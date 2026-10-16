"""Build/check baseline archives and record evidence; never uploads anything."""
import hashlib
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def load(path):
    spec = importlib.util.spec_from_file_location("predictor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.predict


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--starter-kit', type=Path)
    parser.add_argument('--smoke-concurrency', type=int, choices=(1,4), default=1)
    args = parser.parse_args()
    os.environ["PYTHONIOENCODING"] = "utf-8"
    out = ROOT / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True)
    commands = [
        [sys.executable, "tools/build_mean_zip.py"],
        [sys.executable, "check_submission_zip.py", "dist/empirical_mean.zip"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tools", "-p", "test_mean_baseline.py"],
    ]
    records = []
    for i, command in enumerate(commands):
        result = subprocess.run(command, cwd=ROOT / "upstream", capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        (out / f"check_{i}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        records.append({"command": command, "returncode": result.returncode})
        if result.returncode:
            raise RuntimeError(f"Check failed; see {out}")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    candidate = dist / "shrinkage.zip"
    # Fixed timestamps and file permissions make this candidate reproducible byte-for-byte.
    from zipfile import ZipInfo
    with ZipFile(candidate, "w", ZIP_DEFLATED) as archive:
        for name in ("model.py", "README.md"):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, (ROOT / "shrinkage" / name).read_bytes())
    command = [sys.executable, str(ROOT / "upstream/check_submission_zip.py"), str(candidate)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (out / "candidate_check.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    records.append({"command": command, "returncode": result.returncode})
    if result.returncode:
        raise RuntimeError(f"Candidate check failed; see {out}")
    subject = {k: "" for k in ("normalized_name", "provider", "release_date", "access_date", "harness", "harness_version", "reasoning_effort", "subject_features_extra")}
    subject["normalized_name"] = "synthetic-only"
    item = {"item_content": "Synthetic target", "item_features": "", "interactors": "", "benchmark_id": "synthetic-b"}
    target = [subject, item]
    labels = [[[dict(subject), dict(item, item_content=f"Synthetic acquired {i}")], int(i % 3 == 0)] for i in range(31)]
    unrelated = [[[dict(subject, harness="different"), item], 1]] * 31
    unrelated += [[[subject, dict(item, benchmark_id="other-b")], 1]] * 31
    predictors = {"empirical_mean": load(ROOT / "upstream/empirical_mean/model.py"), "shrinkage": load(ROOT / "shrinkage/model.py")}
    checks = {}
    for name, predict in predictors.items():
        checks[name] = {}
        for n in (31, 0, 7, 1, 15, 3, 0):
            p = predict(target, labels[:n])
            expected = ((sum(row[1] for row in labels[:n]) + 1) / (n + 2)
                        if name == "shrinkage" else (sum(row[1] for row in labels[:n]) / n if n else 0.5))
            if p != expected or predict(target, labels[:n] + unrelated) != p:
                raise AssertionError("Budget independence or group isolation failed")
            checks[name][str(n)] = p
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
              (ROOT / "upstream/dist/empirical_mean.zip", candidate, ROOT / "shrinkage/model.py", Path(__file__))}
    revision = subprocess.check_output(["git", "-C", str(ROOT / "upstream"), "rev-parse", "HEAD"], text=True).strip()
    kit_hashes = {}
    if args.starter_kit:
        kit = args.starter_kit.resolve()
        for i, archive in enumerate((ROOT/'upstream/dist/empirical_mean.zip', candidate)):
            # Exercise the actual archive in an isolated directory, not the source checkout.
            with TemporaryDirectory(prefix='archive-', dir=out) as extracted:
                with ZipFile(archive) as bundle:
                    bundle.extractall(extracted)
                checks_to_run = [[sys.executable, str(kit/'tools/check_submission_zip.py'), str(archive)],
                                 [sys.executable, str(kit/'tools/run_smoke_test.py'), extracted,
                                  '--concurrency', str(args.smoke_concurrency)]]
                for j, command in enumerate(checks_to_run):
                    result = subprocess.run(command, cwd=kit, capture_output=True, text=True, encoding='utf-8', errors='replace')
                    (out/f'kit_{i}_{j}.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
                    records.append({'command':command,'returncode':result.returncode})
                    if result.returncode:
                        raise RuntimeError(f'Starter kit check failed; see {out}')
        for file in (kit/'README.md', *sorted((kit/'tools').glob('*.py'))):
            kit_hashes[str(file.relative_to(kit))] = hashlib.sha256(file.read_bytes()).hexdigest()
    evidence = {"status": "LOCAL_INTERFACE_CHECKS_ONLY", "official_submission": False,
                "data": "synthetic interface fixtures only; no performance experiment",
                "python": sys.version, "platform": platform.platform(), "upstream_revision": revision,
                "commands": records, "sha256": hashes, "synthetic_predictions": checks,
                "starter_kit_file_sha256":kit_hashes}
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"PASS: official build, ZIP checks, 4 official tests, budget/group isolation. Evidence: {out}")


if __name__ == "__main__":
    run()
