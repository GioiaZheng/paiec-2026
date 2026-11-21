"""Small independent checks for the new summary statistics."""
import random
import unittest
from analyze import bootstrap, calibration, percentile, reweight


class AnalysisTests(unittest.TestCase):
    def test_quantile_interpolation(self):
        self.assertEqual(percentile([3, 0, 2, 1], .25), .75)

    def test_perfect_and_uninformative_calibration(self):
        perfect = calibration([(0, 0), (1, 1)])
        self.assertEqual(perfect['brier'], 0)
        self.assertEqual(perfect['reliability'], 0)
        self.assertEqual(perfect['resolution'], .25)
        constant = calibration([(.5, 0), (.5, 1)])
        self.assertEqual(constant['brier'], .25)
        self.assertEqual(constant['reliability'], 0)
        self.assertEqual(constant['resolution'], 0)

    def test_response_mixture(self):
        result = calibration([(.25, .5), (.75, 1.)])
        # First case represents two responses; the second has unit pair mass too.
        manual = (.25**2/2+.75**2/2+(.75-1)**2)/2
        self.assertAlmostEqual(result['brier'], manual)

    def test_stratification_and_panel_weighting(self):
        r = bootstrap({'a': [-1., -1., -1.], 'b': [1.]}, random.Random(7), 400)
        self.assertEqual(r['delta'], -.5)
        self.assertEqual(r['pair_interval'], [-.5, -.5])
        self.assertEqual(r['benchmark_interval'], [-1., 1.])

    def test_mixture_zero(self):
        rows = [{'evaluation_rate': q, 'observed_alc': {'beta_1_1': d, 'empirical_mean': 0},
                 'expected_alc': {'beta_1_1': d, 'empirical_mean': 0}} for q, d in [(.05, .1),(.5,-.3)]]
        r = reweight(rows)['observed_alc']
        self.assertAlmostEqual(r['zero_crossing'], .75)
        self.assertAlmostEqual(r['mixtures'][3]['delta'], 0)


if __name__ == '__main__':
    unittest.main()
