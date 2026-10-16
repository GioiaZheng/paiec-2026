"""Check group isolation and exact expectations against exhaustive acquisition."""
import copy
import itertools
import math
import statistics
import unittest

from diagnose_shrinkage import expected_brier
from weaker_shrinkage.model import predict


class WeakerShrinkageTests(unittest.TestCase):
    def test_mixed_groups_and_all_subject_fields(self):
        keys = ('normalized_name', 'provider', 'release_date', 'access_date',
                'harness', 'harness_version', 'reasoning_effort', 'subject_features_extra')
        subject = dict.fromkeys(keys, 'same')
        target = [subject, {'benchmark_id': 'anonymous-a', 'item_content': 'unseen'}]
        labels = [[[subject.copy(), {'benchmark_id': 'anonymous-a'}], 0]]
        labels.append([[subject.copy(), {'benchmark_id': 'anonymous-b'}], 1])
        for key in keys:
            different = {**subject, key: 'different'}
            labels.append([[different, {'benchmark_id': 'anonymous-a'}], 1])
        before = copy.deepcopy(labels)
        self.assertEqual(predict(target, labels), .25)
        self.assertEqual(labels, before)
        self.assertEqual(predict(target, list(reversed(labels))), .25)
        self.assertEqual(predict(target, labels[1:]), .5)
        self.assertEqual(predict(target, []), .5)

    def test_exact_expectation_matches_enumeration(self):
        for cells in ([[0], [1], [1], [0]], [[0, 1, 1], [0], [0, 0, 1], [1, 0]],
                      [[0], [0], [0]], [[1], [1], [1]], [[0, 1, 1]]):
            for n in range(len(cells) + 1):
                for q in (0., .3, 1.):
                    with self.subTest(cells=cells, budget=n, rate=q):
                        values = []
                        for chosen in itertools.combinations(cells, n):
                            weight = 1 / (math.comb(len(cells), n) * math.prod(map(len, chosen)))
                            for labels in itertools.product(*chosen):
                                p = (sum(labels) + .5) / (n + 1)
                                values.append(weight * (q * (1-p)**2 + (1-q)*p*p))
                        result = expected_brier([statistics.fmean(c) for c in cells], q, n, 'beta_0_5_0_5')
                        self.assertAlmostEqual(result['brier'], math.fsum(values), places=12)


if __name__ == '__main__':
    unittest.main()
