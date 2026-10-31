"""Check useful retrieval behavior, prefix isolation and baseline equivalences."""
import copy
import json
import unittest

from retrieval_shrinkage.model import PreparedEvidence, features, predict, weighted_prediction


class RetrievalShrinkageTests(unittest.TestCase):
    def test_zero_label_checker_fixture_without_benchmark_id(self):
        self.assertEqual(predict([{}, {'item_content': 'sample'}], []), .5)

    def test_hand_calculated_similarity_weighting(self):
        prepared = PreparedEvidence([features(t) for t in ('apple apple', 'banana', 'pear')])
        similarities = prepared.similarities(features('apple'))
        self.assertAlmostEqual(similarities[0], 1.)
        self.assertEqual(similarities[1:], [0., 0.])
        # Weights [1.5, .75, .75], plus the original Beta(1,1) pseudo-counts.
        self.assertAlmostEqual(weighted_prediction(similarities, [1, 0, 0]), .5)
        self.assertAlmostEqual(weighted_prediction(similarities, [0, 1, 0]), .35)

    def test_uniform_similarity_and_small_budgets_preserve_baseline(self):
        for labels in ([], [0], [1], [0, 1, 1], [0]*31, [1]*31):
            expected = (1 + sum(labels)) / (len(labels) + 2)
            for cosine in (0., .3, 1.):
                self.assertAlmostEqual(weighted_prediction([cosine]*len(labels), labels), expected)
        self.assertEqual(features('!!!'), {})
        self.assertEqual(PreparedEvidence([features('apple')]).similarities({}), [0.])

    def test_final_user_text_excludes_demonstrations(self):
        prompt = json.dumps([{'role': 'user', 'content': 'old question'},
                             {'role': 'assistant', 'content': 'old answer'},
                             {'role': 'user', 'content': 'New question'}])
        self.assertEqual(features(prompt), features('new question'))
        self.assertEqual(features('CAFÉ café'), features('café CAFÉ'))

    def test_all_subject_fields_and_benchmark_isolation(self):
        subject = dict.fromkeys(('normalized_name', 'provider', 'release_date', 'access_date',
                                 'harness', 'harness_version', 'reasoning_effort', 'subject_features_extra'), 'same')
        item = {'benchmark_id': 'anonymous', 'item_content': 'apple'}
        target = [subject, item]
        evidence = [[[subject, {**item, 'item_content': text}], y]
                    for text, y in (('apple', 1), ('banana', 0), ('pear', 0))]
        expected = predict(target, evidence)
        for key in subject:
            evidence.append([[{**subject, key: 'different'}, item], 0])
        evidence.append([[subject, {**item, 'benchmark_id': 'different'}], 0])
        before = copy.deepcopy(evidence)
        self.assertAlmostEqual(predict(target, evidence), expected)
        self.assertAlmostEqual(predict(target, list(reversed(evidence))), expected)
        self.assertEqual(evidence, before)
        changed = [target, [[subject, {**item, 'item_content': 'apple'}], 0]]
        self.assertEqual(predict(changed[0], [changed[1]]), 1/3)


if __name__ == '__main__':
    unittest.main()
