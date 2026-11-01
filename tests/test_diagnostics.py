"""Check acquisition expectations against enumeration, including repeated outcomes."""
import itertools
import math
import statistics
import unittest

from diagnose_shrinkage import expected_brier, METHODS


class ExactExpectationTests(unittest.TestCase):
    def test_matches_every_possible_acquisition(self):
        fixtures = ([[0], [1], [1], [0]],
                    [[0, 1, 1], [0], [0, 0, 1], [1, 0]],
                    [[0], [0], [0]], [[1], [1], [1]], [[0, 1, 1]])
        for cells in fixtures:
            means = [statistics.fmean(c) for c in cells]
            for n in range(len(cells) + 1):
                for q in (0., .3, 1.):
                    for method in METHODS:
                        with self.subTest(cells=cells, budget=n, q=q, method=method):
                            total = 0.
                            for chosen in itertools.combinations(cells, n):
                                weight = 1 / (math.comb(len(cells), n) * math.prod(len(c) for c in chosen))
                                for labels in itertools.product(*chosen):
                                    if not n or method == 'constant_0.5':
                                        p = .5
                                    elif method == 'empirical_mean':
                                        p = sum(labels) / n
                                    else:
                                        p = (sum(labels) + 1) / (n + 2)
                                    total += weight * (q * (1-p)**2 + (1-q) * p**2)
                            self.assertAlmostEqual(expected_brier(means, q, n, method)['brier'], total, places=12)

    def test_full_pool_retains_response_sampling_variance(self):
        # Sampling all items removes item-selection variance, but not the choice
        # between independent stored response runs for an item.
        result = expected_brier([.5, .5], .5, 2, 'empirical_mean')
        self.assertAlmostEqual(result['variance'], .125)
        self.assertAlmostEqual(result['brier'], .375)


if __name__ == '__main__':
    unittest.main()
