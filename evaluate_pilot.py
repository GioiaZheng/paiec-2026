"""Fixed, no-fit comparison on public benchmarks. No network or GPU.

Run with Python 3.12 after installing requirements-local.txt into .deps.
No grading criteria, reference answers, traces or test conditions enter predictors.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".deps"))
import pyarrow
import pyarrow.parquet as pq
import collections
import argparse
import hashlib
import importlib.util
import json
import random
import unicodedata
from datetime import datetime, timezone
from near_duplicates import audit_items
from bertaqa_groups import audit_bertaqa

REVISION = "54074453da7b9911be0f48e4c560be547bc84d21"
BENCHMARKS = ("multi_swebench", "researchcodebench")
SEEDS = (20261016, 20261017, 20261018)
BUDGETS = (0, 1, 3, 7, 15, 31)
WEIGHTS = (.1, .2, .2, .2, .2, .1)
SUBJECT_KEYS = ("normalized_name", "provider", "release_date", "access_date", "harness", "harness_version", "reasoning_effort", "subject_features_extra")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())


def load_predict(path):
    spec = importlib.util.spec_from_file_location("predictor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.predict


def read(benchmark, name, columns=None):
    return pq.read_table(ROOT / "data" / benchmark / f"{name}.parquet", columns=columns).to_pylist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split-unit', choices=('near', 'exact', 'item', 'source'), default='near')
    parser.add_argument('--protocol', type=Path, help='Frozen validation configuration')
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding='utf-8')) if args.protocol else None
    benchmarks = tuple(protocol['benchmarks']) if protocol else BENCHMARKS
    if not benchmarks or len(set(benchmarks)) != len(benchmarks):
        raise ValueError('Expected a nonempty list of distinct benchmarks')
    if any(Path(b).name != b or '/' in b or '\\' in b or b in ('.', '..') for b in benchmarks):
        raise ValueError('Benchmark names must be directory names')
    if protocol:
        for key, expected in {'revision': REVISION, 'seeds': list(SEEDS), 'split_seed': SEEDS[0],
                              'budgets': list(BUDGETS), 'weights': list(WEIGHTS),
                              'near_duplicate_threshold': .9}.items():
            if protocol[key] != expected:
                raise ValueError(f'Unsupported protocol setting: {key}')
        if args.split_unit not in (protocol['primary_split'], protocol['sensitivity_split']):
            raise ValueError('Split is not specified by the protocol')
        for name, expected in protocol['method_sha256'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
                raise ValueError(f'Predictor changed after protocol freeze: {name}')
    source_policy = protocol and protocol.get('duplicate_policy') == 'bertaqa-source-question-v1'
    if source_policy and benchmarks != ('bertaqa',):
        raise ValueError('BertaQA source grouping requires a BertaQA-only run')
    if args.split_unit == 'source' and not source_policy:
        raise ValueError('Source grouping needs a supported frozen protocol')
    out = ROOT / "runs" / ("pilot-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    out.mkdir(parents=True)
    sources = {}
    data = {}
    audit = {}
    # All downloaded tables must be listed and hashed; source URLs are revision-pinned.
    for benchmark in benchmarks:
        for name in ('benchmarks', 'items', 'subjects', 'responses'):
            file = ROOT / 'data' / benchmark / f'{name}.parquet'
            sources[file.relative_to(ROOT).as_posix()] = {
                "bytes": file.stat().st_size, "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                "url": f"https://huggingface.co/datasets/aims-foundations/measurement-db/resolve/{REVISION}/{benchmark}/formatted_tables/{file.name}"}
        meta, = read(benchmark, "benchmarks")
        if (meta["release"], meta["response_type"], meta["granularity"]) != ("public", "binary", "item"):
            raise ValueError(f"Ineligible benchmark: {benchmark}")
        subjects = read(benchmark, "subjects")
        item_columns = ["item_id", "benchmark_id", "content", "item_features"]
        if source_policy:
            item_columns.append('raw_item_id')
        items = read(benchmark, "items", item_columns)
        responses = read(benchmark, "responses")
        if len({s["subject_id"] for s in subjects}) != len(subjects) or len({i["item_id"] for i in items}) != len(items):
            raise ValueError("Nonunique join key")
        if len({r["response_id"] for r in responses}) != len(responses):
            raise ValueError("Duplicate response_id")
        subject_map = {s["subject_id"]: {k: str(s[k]).strip() if s[k] is not None else "" for k in SUBJECT_KEYS} for s in subjects}
        item_map = {i["item_id"]: i for i in items}
        hashes = {i["item_id"]: digest(normalize(i["content"])) for i in items}
        missing_content = sum(not normalize(i["content"]) for i in items)
        groups = collections.defaultdict(lambda: collections.defaultdict(list))
        missing = 0
        conditions = collections.Counter()
        for r in responses:
            if r["benchmark_id"] != benchmark or r["subject_id"] not in subject_map or r["item_id"] not in item_map:
                raise ValueError("Broken join or benchmark mismatch")
            if r["response"] is None:
                missing += 1
                continue
            if r["response"] not in (0., 1.):
                raise ValueError("Nonbinary observed grade")
            key = json.dumps(subject_map[r["subject_id"]], sort_keys=True)
            groups[key][r["item_id"]].append(r)
            conditions[str(r["test_condition"])] += 1
        audit[benchmark] = {
            "license": meta["license"], "items": len(items), "subjects": len(subjects),
            "visible_subject_groups": len(groups), "responses": len(responses), "missing_grades_excluded": missing,
            "empty_item_content": missing_content, "normalized_text_duplicate_items": len(items) - len(set(hashes.values())),
            "test_condition_counts": dict(conditions), "eligible_pairs": sum(len(v) >= 80 for v in groups.values())}
        cells = [rows for group in groups.values() for rows in group.values()]
        audit[benchmark]['repeated_response_cells'] = sum(len(rows) > 1 for rows in cells)
        audit[benchmark]['cells_with_disagreeing_outcomes'] = sum(len({r['response'] for r in rows}) > 1 for rows in cells)
        if missing_content:
            raise ValueError("Empty content requires an explicit grouping policy")
        data[benchmark] = (subject_map, item_map, hashes, groups)
    hash_benchmarks = collections.defaultdict(set)
    for b, (_, _, hashes, _) in data.items():
        for value in hashes.values():
            hash_benchmarks[value].add(b)
    shared = {h for h, names in hash_benchmarks.items() if len(names) > 1}
    audit["cross_benchmark_normalized_exact_hash_overlap"] = len(shared)
    if source_policy:
        source_groups, lexical_audit = audit_bertaqa(data['bertaqa'][1])
        cluster_map = {f'bertaqa/{item_id}': group for item_id, group in source_groups.items()}
    else:
        cluster_map, lexical_audit = audit_items({f'{b}/{item_id}': item['content']
                                                for b, (_, items, _, _) in data.items()
                                                for item_id, item in items.items()})
    lexical_audit['cross_benchmark_pairs'] = sum(p['left'].split('/')[0] != p['right'].split('/')[0]
                                               for p in lexical_audit['pairs'])
    audit['near_duplicates'] = {k:v for k,v in lexical_audit.items() if k != 'pairs'}
    (out/'duplicate_pairs.json').write_text(json.dumps(lexical_audit,indent=2),encoding='utf-8')
    audit["reference_answer_policy"] = "Excluded grading_criterion, verifier, asset_manifest and traces from predictor inputs"
    mean = load_predict(ROOT / "upstream/empirical_mean/model.py")
    shrink = load_predict(ROOT / "shrinkage/model.py")
    methods = {"constant_0.5": lambda target, labeled: .5, "empirical_mean": mean, "beta_1_1": shrink}
    scores = []
    trajectories = []
    for benchmark, (_, items, hashes, groups) in data.items():
        for subject_json, observations in sorted(groups.items()):
            if len(observations) < 80:
                continue
            subject = json.loads(subject_json)
            pair = digest(benchmark + subject_json)
            # Label-blind lexical clusters protect both repeated and near-duplicate text.
            clusters = collections.defaultdict(list)
            for item_id in observations:
                key = (cluster_map[f'{benchmark}/{item_id}'] if args.split_unit in ('near', 'source')
                       else hashes[item_id] if args.split_unit == 'exact' else item_id)
                clusters[key].append(item_id)
            for ids in clusters.values():
                ids.sort()
            for seed in SEEDS:
                split_rng = random.Random(int(digest(f"{pair}:{SEEDS[0]}:split"), 16))
                cluster_keys = sorted(clusters)
                split_rng.shuffle(cluster_keys)
                boundary = (len(cluster_keys) + 1) // 2
                acquisition_keys = cluster_keys[:boundary]
                evaluation_keys = cluster_keys[boundary:]
                rng = random.Random(int(digest(f"{pair}:{seed}:acquire"), 16))
                acquisition_ids = [item_id for key in acquisition_keys for item_id in clusters[key]]
                evaluation_ids = [item_id for key in evaluation_keys for item_id in clusters[key]]
                # Randomize individual candidates after the guarded pool split.
                # Keeping cluster members adjacent would bias the revealed set.
                rng.shuffle(acquisition_ids)
                if len(acquisition_ids) < 31 or not evaluation_ids:
                    raise ValueError("Insufficient distinct acquisition/evaluation items")
                if args.split_unit != 'item' and {hashes[x] for x in acquisition_ids} & {hashes[x] for x in evaluation_ids}:
                    raise AssertionError("Exact text leakage")
                if args.split_unit in ('near', 'source') and ({cluster_map[f'{benchmark}/{x}'] for x in acquisition_ids}
                                                & {cluster_map[f'{benchmark}/{x}'] for x in evaluation_ids}):
                    raise AssertionError('Lexical cluster leakage')
                revealed = []
                selected = []
                # One recorded response per acquired distinct item, sampled reproducibly.
                for item_id in acquisition_ids[:31]:
                    row = rng.choice(sorted(observations[item_id], key=lambda r:r["response_id"]))
                    item = {"item_content": items[item_id]["content"], "item_features": (items[item_id]["item_features"] or "").strip(),
                            "interactors": (row["interactors"] or "").strip(), "benchmark_id": benchmark}
                    revealed.append([[subject, item], int(row["response"])])
                    selected.append(row["response_id"])
                evaluation_rows = [r for item_id in evaluation_ids for r in observations[item_id]]
                target = [subject, {"item_content": "", "item_features": "", "interactors": "", "benchmark_id": benchmark}]
                # These predictors are constant within the pair, so aggregate exactly over all responses.
                positives = sum(r["response"] for r in evaluation_rows)
                count = len(evaluation_rows)
                trajectories.append({"pair": pair, "benchmark": benchmark, "seed": seed,
                                     "acquisition_item_ids": acquisition_ids, "evaluation_item_ids": evaluation_ids,
                                     "revealed_response_ids": selected, "subject": subject})
                if source_policy:
                    trajectories[-1]['source_group_overlap'] = len({source_groups[x] for x in acquisition_ids}
                                                                  & {source_groups[x] for x in evaluation_ids})
                for name, predict in methods.items():
                    briers = []
                    probabilities = []
                    for n in BUDGETS:
                        p = predict(target, revealed[:n])
                        if not isinstance(p, float) or not 0 <= p <= 1:
                            raise ValueError("Invalid probability")
                        probabilities.append(p)
                        briers.append((positives*(1-p)**2 + (count-positives)*p**2)/count)
                    scores.append({"benchmark": benchmark, "pair": pair, "seed": seed, "method": name,
                                   "evaluation_responses": count, "evaluation_items": len(evaluation_ids),
                                   "evaluation_success_rate": positives/count, "probabilities": probabilities,
                                   "briers": briers, "alc": sum(w*b for w,b in zip(WEIGHTS,briers))})
    summary = []
    for benchmark in (*benchmarks, "ALL_PAIRS"):
        for name in methods:
            rows = [r for r in scores if r["method"] == name and (benchmark == "ALL_PAIRS" or r["benchmark"] == benchmark)]
            if not rows:
                raise ValueError(f'No eligible groups for {benchmark}; retain and report this outcome')
            summary.append({"benchmark": benchmark, "method": name, "pairs": len({r["pair"] for r in rows}),
                            "seed_repetitions": len(SEEDS), "alc": sum(r["alc"] for r in rows)/len(rows),
                            "briers": [sum(r["briers"][i] for r in rows)/len(rows) for i in range(6)]})
    config = {"status": "FIXED_LOCAL_VALIDATION" if protocol else "EXPLORATORY_PUBLIC_DATA_PILOT",
              "benchmarks": benchmarks, "revision": REVISION, "seeds": SEEDS,
              "budgets": BUDGETS, "weights": WEIGHTS, "fit": False, "tuning": False,
              "python": sys.version, "pyarrow": pyarrow.__version__, "gpu_used": False,
              "split_unit": args.split_unit, "near_duplicate_threshold": .9,
              "limitations": ["Limited public benchmarks; not an official private test",
                              "Lexical duplicate check does not detect semantic paraphrases or translations",
                              "Near/exact splits halve cluster counts, not item counts; item split halves item counts",
                              "Random acquisition is distribution-compatible; anonymous platform IDs prevent exact trajectory matching",
                              "No benchmark-level uncertainty intervals; seeds share the evaluation pool",
                              "Source data are not redistributed; per-benchmark licenses are recorded in audit.json"],
              "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                [Path(__file__), ROOT/'near_duplicates.py', ROOT/'bertaqa_groups.py', ROOT/'shrinkage/model.py', ROOT/'upstream/empirical_mean/model.py']}}
    if protocol:
        config['protocol_sha256'] = hashlib.sha256(args.protocol.read_bytes()).hexdigest()
        (out/'protocol.json').write_bytes(args.protocol.read_bytes())
    for name, value in [("manifest",sources),("audit",audit),("config",config),("summary",summary),("scores",scores),("trajectories",trajectories)]:
        (out / f"{name}.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps({"output":str(out),"audit":audit,"summary":summary}, indent=2))


if __name__ == "__main__":
    main()
