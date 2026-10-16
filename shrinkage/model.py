"""Experimental Beta(1, 1) shrinkage; standard library only, no retained state."""


def predict(input: list[dict], labeled: list | None = None) -> float:
    subject, item = input
    if not labeled:
        return 0.5
    benchmark = item.get("benchmark_id")
    if not isinstance(benchmark, str) or not benchmark:
        raise ValueError("A nonempty benchmark_id is required")
    successes = count = 0
    for (other_subject, other_item), label in labeled:
        if other_subject != subject:
            continue
        other_benchmark = other_item.get("benchmark_id")
        if not isinstance(other_benchmark, str) or not other_benchmark:
            raise ValueError("Acquired items require benchmark_id")
        if other_benchmark != benchmark:
            continue
        if label not in (0, 1):
            raise ValueError("Expected binary outcomes")
        successes += label
        count += 1
    return float((successes + 1) / (count + 2))
