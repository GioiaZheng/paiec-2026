"""Group BertaQA translations and prompt variants without reading outcomes."""
import collections
import json
import re

from near_duplicates import audit_items, normalized


def source_question(raw_id):
    match = re.fullmatch(r'(en|eu)-([0-9]+)', raw_id)
    if not match:
        raise ValueError(f'Unexpected BertaQA source ID: {raw_id}')
    return match.group(2)


def audit_bertaqa(items):
    questions = {}
    representatives = {}
    metadata = collections.defaultdict(set)
    for item_id, row in sorted(items.items()):
        raw = row['raw_item_id']
        question_id = source_question(raw)
        messages = json.loads(row['content'])
        if not messages or messages[-1]['role'] != 'user':
            raise ValueError('Expected a final user question')
        question = normalized(messages[-1]['content'])
        if raw in questions and questions[raw] != question:
            raise ValueError('One raw ID has conflicting target questions')
        questions[raw] = question
        representatives.setdefault(raw, item_id)
        features = dict(part.split('=', 1) for part in row['item_features'].split(';'))
        if features['lang'] != raw.split('-')[0]:
            raise ValueError('Language disagrees with raw ID')
        metadata[question_id].add(tuple(features[k] for k in ('category', 'difficulty', 'group')))
    if any(len(values) != 1 for values in metadata.values()):
        raise ValueError('Parallel question metadata disagree')
    # Compare unique final questions; shared few-shot examples must not dominate similarity.
    _, lexical = audit_items(questions)
    parents = {source_question(raw): source_question(raw) for raw in questions}

    def find(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    for pair in lexical['pairs']:
        left, right = find(source_question(pair['left'])), find(source_question(pair['right']))
        parents[max(left, right)] = min(left, right)
    groups = {item_id: 'bertaqa/source/' + find(source_question(row['raw_item_id']))
              for item_id, row in items.items()}
    # Store representative item links so a separate verifier can reconstruct the guard.
    lexical['pairs'] = [dict(pair, left='bertaqa/' + representatives[pair['left']],
                            right='bertaqa/' + representatives[pair['right']])
                        for pair in lexical['pairs']]
    lexical['comparison_unit'] = 'Unique language-qualified final questions, excluding few-shot examples'
    lexical['source_questions'] = len(metadata)
    lexical['guarded_source_groups'] = len(set(groups.values()))
    lexical['prompt_variants'] = len(items)
    return groups, lexical
