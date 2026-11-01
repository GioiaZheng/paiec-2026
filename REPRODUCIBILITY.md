# Reproducibility

Use Python 3.12 and a full Git clone. The report refers to
[`d2d3e3c1e803880f4918f2f8065616b513731a40`](https://github.com/GioiaZheng/paiec-2026/tree/d2d3e3c1e803880f4918f2f8065616b513731a40).
The directory cleanup preserves the experiment sources, configurations, recorded
hashes and aggregate results. Submission archives are not stored in Git.

## Checks

Obtain the pinned official baseline using the commands in the [README](README.md),
then run from the repository root:

```bash
python -m unittest discover -s tests -t . -v
python reproduce_extensions.py --check-sources
python run_baseline.py
```

CI runs these same checks: 19 unit tests, frozen-source verification, four
official empirical-mean tests, ZIP checks and group/budget isolation checks.
They use only the standard library and synthetic inputs. On Windows, use
`python -X utf8` if the console cannot display the workspace path.

`run_baseline.py` creates archives under `dist/` and logs under `runs/`.
Run it in a separate checkout if you need to preserve an existing archive.

For the organizer's smoke test, obtain the starting kit from CodaBench's
**Get Started → Files** tab and unpack it under `local/official/starting_kit`:

```bash
python run_baseline.py --starter-kit local/official/starting_kit
```

The kit's sample score is an interface check. Its parallel worker helper requires
Linux/WSL; the recorded ZIP and smoke checks are in
[interface_checks.json](results/2026-10-16/interface_checks.json).
The separate archive replay is documented at the submitted revision and its
[aggregate evidence](results/2026-10-16/runtime_replay.json) remains unchanged.

## Rebuild the follow-up experiments

```bash
python -m pip install --target .deps -r requirements-local.txt
python -X utf8 reproduce_extensions.py --data data --output local/replication
```

Download the 24 pinned tables listed in
[Follow-up reproduction](docs/extensions-reproduction.md) before running the
second command. The driver verifies their hashes and restores the unchanged
experiment files from `experiments/` and `tests/` to their original layout in
the new workspace. The archived driver itself is read from the submitted Git
revision, so a shallow clone or a downloaded source ZIP is insufficient.

No original run directories or saved predictions are needed. The driver rebuilds
eight splits and four comparisons, independently rescores the lexical predictions,
and compares the aggregates within `1e-12`. This repeats existing evidence;
it is not a new validation experiment. Full outputs remain local.

## Individual analyses at the submitted revision

The experiment scripts retain their original paths internally to preserve the
recorded source hashes. For individual pilots, the weaker-prior ablation,
diagnostics or archive replay, use a separate checkout of the submitted version:

```bash
git clone --config core.autocrlf=false https://github.com/GioiaZheng/paiec-2026.git local/submitted-code
git -C local/submitted-code checkout d2d3e3c1e803880f4918f2f8065616b513731a40
```

Follow that checkout's
[manual instructions](https://github.com/GioiaZheng/paiec-2026/blob/d2d3e3c1e803880f4918f2f8065616b513731a40/REPRODUCIBILITY.md)
from its root, including dependency, upstream baseline and data setup.
Do not run the files directly inside `experiments/`.

Data come from measurement-db revision
`54074453da7b9911be0f48e4c560be547bc84d21` through authorized access.
Dataset licenses are separate from the code license; source tables, credentials,
private feedback and item-level traces are not redistributed.
