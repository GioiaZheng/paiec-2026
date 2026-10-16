"""Small checks for the duplicate guard and scoring contract."""
import itertools
import random
import unittest
import json
from bertaqa_groups import audit_bertaqa
from near_duplicates import audit_items, shingles


class DuplicateAuditTests(unittest.TestCase):
    def test_prefix_filter_matches_exhaustive_search(self):
        rng = random.Random(42)
        base = [f"token{i}" for i in range(120)]
        records = {}
        for i in range(25):
            tokens = base.copy()
            for _ in range(rng.randrange(0, 15)):
                tokens[rng.randrange(len(tokens))] = f"replacement{rng.randrange(20)}"
            records[str(i)] = " ".join(tokens)
        records['other'] = 'unrelated short question'
        _, audit = audit_items(records)
        expected = set()
        for a, b in itertools.combinations(sorted(records), 2):
            left, right = shingles(records[a]), shingles(records[b])
            if len(left & right) / len(left | right) >= .9:
                expected.add((a, b))
        self.assertEqual({(p['left'], p['right']) for p in audit['pairs']}, expected)

    def test_whitespace_and_case_copies_share_cluster(self):
        clusters, _ = audit_items({'a':'Solve THE task', 'b':' solve  the\nTASK ', 'c':'different task'})
        self.assertEqual(clusters['a'], clusters['b'])
        self.assertNotEqual(clusters['a'], clusters['c'])


class SourceQuestionTests(unittest.TestCase):
    @staticmethod
    def item(raw, question, demonstration='example'):
        return {'raw_item_id': raw,
                'content': json.dumps([{'role': 'assistant', 'content': demonstration},
                                       {'role': 'user', 'content': question}]),
                'item_features': f'category=culture;difficulty=1;group=local;lang={raw[:2]};shot=5'}

    def test_translations_and_prompt_variants_stay_together(self):
        records = {'a': self.item('en-7', 'Who invented this instrument?'),
                   'b': self.item('en-7', 'Who invented this instrument?', 'different example'),
                   'c': self.item('eu-7', 'Nork asmatu zuen tresna hau?'),
                   'd': self.item('en-8', 'Which city has the oldest university?')}
        groups, audit = audit_bertaqa(records)
        self.assertEqual(len({groups[k] for k in ('a', 'b', 'c')}), 1)
        self.assertNotEqual(groups['a'], groups['d'])
        self.assertEqual(audit['source_questions'], 2)

    def test_conflicting_raw_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'conflicting target'):
            audit_bertaqa({'a': self.item('en-7', 'First question'),
                          'b': self.item('en-7', 'Unrelated question')})


if __name__ == '__main__':
    unittest.main()
