"""Independent sequential evidence, exhaustive acquisition, and isolation checks."""
import copy
import itertools
import math
import statistics
import unittest

from acquisition_distribution import success_distributions
from adaptive_prior import posterior, predict


class AdaptivePriorTests(unittest.TestCase):
    def test_marginal_evidence_matches_sequential_prediction(self):
        for center in (.001, .2, .5, .8, .999):
            for n in (0, 1, 3, 7, 15, 31):
                for s in range(n + 1):
                    labels = [1] * s + [0] * (n - s)
                    likelihoods = []
                    means = []
                    for a, b in ((1., 1.), (2 * center, 2 * (1 - center))):
                        likelihood = 1.
                        for y in labels:
                            likelihood *= (a if y else b) / (a + b)
                            a += y
                            b += 1-y
                        likelihoods.append(likelihood)
                        means.append(a / (a + b))
                    expected_weight = likelihoods[1] / sum(likelihoods)
                    expected_p = sum(l*m for l, m in zip(likelihoods, means)) / sum(likelihoods)
                    actual_p, actual_weight = posterior(s, n, center)
                    self.assertAlmostEqual(actual_p, expected_p, places=12)
                    self.assertAlmostEqual(actual_weight, expected_weight, places=12)
                    self.assertGreaterEqual(actual_p, 0.)
                    self.assertLessEqual(actual_p, 1.)

    def test_acquisition_distribution_matches_exhaustive_draws(self):
        for cells in ([[0], [1], [1], [0]], [[0, 1, 1], [0], [1, 0]], [[1]], [[0, 1, 1]]):
            budgets = list(range(len(cells) + 1))
            actual = success_distributions([statistics.fmean(c) for c in cells], budgets)
            for n in budgets:
                expected = [0.] * (n + 1)
                for chosen in itertools.combinations(cells, n):
                    weight = 1 / (math.comb(len(cells), n) * math.prod(map(len, chosen)))
                    for labels in itertools.product(*chosen):
                        expected[sum(labels)] += weight
                for left, right in zip(actual[n], expected):
                    self.assertAlmostEqual(left, right, places=12)
            reversed_pool = success_distributions([statistics.fmean(c) for c in reversed(cells)], budgets)
            for n in budgets:
                for left, right in zip(actual[n], reversed_pool[n]):
                    self.assertAlmostEqual(left, right, places=12)

    def test_label_isolation_and_adaptation_direction(self):
        subject = dict.fromkeys(('normalized_name', 'provider', 'release_date', 'access_date',
                                 'harness', 'harness_version', 'reasoning_effort', 'subject_features_extra'), 'same')
        target = [subject, {'benchmark_id': 'anonymous'}]
        evidence = [[target, 1]]
        for key in subject:
            evidence.append([[{**subject, key: 'different'}, target[1]], 0])
        evidence.append([[subject, {'benchmark_id': 'different'}], 0])
        before = copy.deepcopy(evidence)
        self.assertAlmostEqual(predict(target, evidence, .25), 11/18)
        self.assertEqual(predict(target, evidence, .25), predict(target, evidence[::-1], .25))
        self.assertEqual(predict(target, [], .25), .375)
        self.assertEqual(evidence, before)
        self.assertLess(posterior(1, 1, .25)[1], .5)
        self.assertGreater(posterior(0, 1, .25)[1], .5)
        self.assertEqual(posterior(4, 7, .5)[0], 5/9)


if __name__ == '__main__':
    unittest.main()
