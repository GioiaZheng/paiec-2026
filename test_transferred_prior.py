"""Check fold leakage, subject isolation and finite-pool expectations."""
import copy
import itertools
import math
import statistics
import unittest

from transferred_prior import expected_brier, fit_center, predict


class TransferredPriorTests(unittest.TestCase):
    def test_held_out_outcomes_cannot_change_prior(self):
        rates = {'held': [.1, .9], 'first': [.2, .4], 'second': [.8]}
        center, training = fit_center(rates, 'held')
        self.assertAlmostEqual(center, .55)
        self.assertEqual(training, ['first', 'second'])
        rates['held'] = [float('nan')]  # A leaked target read would fail validation.
        self.assertEqual(fit_center(rates, 'held'), (center, training))
        rates['first'] = [1., 1.]
        self.assertNotEqual(fit_center(rates, 'held')[0], center)

    def test_all_subject_fields_and_benchmark_are_isolated(self):
        subject = dict.fromkeys(('normalized_name', 'provider', 'release_date',
                                 'access_date', 'harness', 'harness_version',
                                 'reasoning_effort', 'subject_features_extra'), 'same')
        target = [subject, {'benchmark_id': 'anonymous'}]
        labels = [[target, 1]]
        for key in subject:
            labels.append([[{**subject, key: 'different'}, target[1]], 0])
        labels.append([[subject, {'benchmark_id': 'elsewhere'}], 0])
        before = copy.deepcopy(labels)
        self.assertEqual(predict(target, labels, .25), .5)
        self.assertEqual(predict(target, labels[::-1], .25), .5)
        self.assertEqual(predict(target, [], .25), .25)
        self.assertEqual(labels, before)

    def test_expectation_matches_exhaustive_acquisition(self):
        cells = [[0, 1, 1], [0], [1, 0]]
        for n, center, q in itertools.product(range(4), (0., .2, .5, 1.), (0., .3, 1.)):
            terms = []
            for chosen in itertools.combinations(cells, n):
                weight = 1 / (math.comb(len(cells), n) * math.prod(map(len, chosen)))
                for labels in itertools.product(*chosen):
                    p = (sum(labels) + 2 * center) / (n + 2)
                    terms.append(weight * (q * (1 - p)**2 + (1 - q)*p*p))
            actual = expected_brier([statistics.fmean(c) for c in cells], q, n, center)
            self.assertAlmostEqual(actual, math.fsum(terms), places=12)


if __name__ == '__main__':
    unittest.main()
