"""Bayesian mixture of neutral and transferred priors; development adapter."""
import math


def posterior(successes, count, center):
    """Return posterior predictive probability and transferred-component weight.

    Components are Beta(1,1) and Beta(2*center, 2*(1-center)), initially equiprobable.
    The binomial coefficient cancels from the component evidence ratio.
    """
    if not isinstance(count, int) or not isinstance(successes, int) or not 0 <= successes <= count:
        raise ValueError('Expected integer successes and nonnegative count')
    if not math.isfinite(center) or not 0 < center < 1:
        raise ValueError('A proper prior requires center strictly between zero and one')
    evidence = []
    for a, b in ((1., 1.), (2 * center, 2 * (1 - center))):
        evidence.append(math.lgamma(a + successes) + math.lgamma(b + count - successes)
                        - math.lgamma(a + b + count)
                        - math.lgamma(a) - math.lgamma(b) + math.lgamma(a + b))
    top = max(evidence)
    likelihoods = [math.exp(x - top) for x in evidence]
    weight = likelihoods[1] / math.fsum(likelihoods)
    neutral = (successes + 1) / (count + 2)
    transferred = (successes + 2 * center) / (count + 2)
    return (1 - weight) * neutral + weight * transferred, weight


def predict(input, labeled, center):
    """Only revealed labels matching the full subject and benchmark affect weights."""
    subject, item = input
    benchmark = item.get('benchmark_id')
    if not isinstance(benchmark, str) or not benchmark:
        raise ValueError('Expected a nonempty benchmark ID')
    successes = count = 0
    for (other_subject, other_item), label in labeled or []:
        if other_subject != subject or other_item.get('benchmark_id') != benchmark:
            continue
        if label not in (0, 1):
            raise ValueError('Expected binary outcomes')
        successes += int(label)
        count += 1
    return float(posterior(successes, count, center)[0])
