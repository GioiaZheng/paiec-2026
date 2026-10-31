"""Development-only prior-center transfer; no test outcomes enter fitting."""
import math
import statistics


def fit_center(group_rates, held_out):
    """Average groups within each training benchmark, then benchmarks equally."""
    training = {b: rates for b, rates in group_rates.items() if b != held_out}
    if held_out not in group_rates or not training:
        raise ValueError("Expected a held-out benchmark and nonempty training set")
    if any(not rates or any(not math.isfinite(p) or not 0 <= p <= 1
                            for p in rates) for rates in training.values()):
        raise ValueError("Invalid training group rates")
    center = statistics.fmean(statistics.fmean(rates) for rates in training.values())
    return center, sorted(training)


def predict(input, labeled, center):
    """Experimental adapter; center is fitted before held-out evaluation."""
    if not math.isfinite(center) or not 0 <= center <= 1:
        raise ValueError("Invalid prior center")
    subject, item = input
    benchmark = item.get('benchmark_id')
    if not isinstance(benchmark, str) or not benchmark:
        raise ValueError("A nonempty benchmark_id is required")
    successes = count = 0
    for (other_subject, other_item), label in labeled or []:
        if other_subject != subject:
            continue
        if other_item.get('benchmark_id') != benchmark:
            continue
        if label not in (0, 1):
            raise ValueError("Expected binary outcomes")
        successes += label
        count += 1
    return (successes + 2 * center) / (count + 2)


def expected_brier(item_rates, evaluation_rate, budget, center):
    """Exact acquisition expectation, conditional on the recorded fixed pools."""
    size = len(item_rates)
    if (not size or not 0 <= budget <= size or not 0 <= center <= 1
            or not 0 <= evaluation_rate <= 1
            or any(not 0 <= p <= 1 for p in item_rates)):
        raise ValueError("Invalid pool, budget, rate or center")
    average = statistics.fmean(item_rates)
    within = statistics.fmean(p * (1 - p) for p in item_rates)
    between = statistics.fmean((p - average) ** 2 for p in item_rates)
    correction = (size - budget) / (size - 1) if size > 1 else 0
    variance = budget * (within + correction * between) / (budget + 2) ** 2
    mean = (budget * average + 2 * center) / (budget + 2)
    return variance + (mean - evaluation_rate) ** 2 + evaluation_rate * (1 - evaluation_rate)
