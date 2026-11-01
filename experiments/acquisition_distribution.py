"""Exact success-count distribution for uniform acquisition without replacement.

Each selected item contributes one uniformly sampled recorded response. The
distribution is for offline diagnostics, never a predictor input.
"""
import math


def success_distributions(item_rates, budgets):
    size = len(item_rates)
    if (not size or not budgets or any(not isinstance(n, int) or not 0 <= n <= size for n in budgets)
            or any(not math.isfinite(p) or not 0 <= p <= 1 for p in item_rates)):
        raise ValueError('Invalid pool, budgets or item rates')
    if all(p in (0, 1) for p in item_rates):
        successes = int(sum(item_rates))
        failures = size - successes
        return {n: [math.comb(successes, s) * math.comb(failures, n-s) / math.comb(size, n)
                    if s <= successes and n-s <= failures else 0. for s in range(n + 1)]
                for n in budgets}
    maximum = max(budgets)
    dp = [[1.]] + [[0.] * (n + 1) for n in range(1, maximum + 1)]
    for i, rate in enumerate(item_rates, 1):
        for n in range(min(i, maximum), 0, -1):
            include = n / i
            previous = dp[n-1]
            dp[n] = [(1 - include) * dp[n][s] + include * (
                ((1 - rate) * previous[s] if s < n else 0.)
                + (rate * previous[s-1] if s else 0.)) for s in range(n + 1)]
    result = {n: dp[n] for n in budgets}
    for values in result.values():
        if not math.isclose(math.fsum(values), 1., abs_tol=1e-12, rel_tol=0):
            raise AssertionError('Acquisition probabilities do not sum to one')
    return result
