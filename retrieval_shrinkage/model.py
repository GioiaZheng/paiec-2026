"""Bounded TF-IDF reweighting of revealed labels; standard library only."""
from collections import Counter
import json
import math
import re
import unicodedata


def features(content):
    """Use the final user message when content is a serialized chat prompt."""
    if not isinstance(content, str):
        raise ValueError('item_content must be a string')
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, list):
        users = [m['content'] for m in parsed if isinstance(m, dict)
                 and m.get('role') == 'user' and isinstance(m.get('content'), str)]
        if users:
            content = users[-1]
    tokens = re.findall(r'\w+', unicodedata.normalize('NFKC', content).casefold())
    return {term: 1 + math.log(count) for term, count in Counter(tokens).items()}


def weighted_prediction(similarities, labels):
    n = len(labels)
    if len(similarities) != n or any(y not in (0, 1) for y in labels):
        raise ValueError('Invalid evidence')
    if any(not math.isfinite(c) or not 0 <= c <= 1 for c in similarities):
        raise ValueError('Cosine similarities must be in [0,1]')
    if n < 2:
        return (1 + sum(labels)) / (n + 2)
    # Relative weights (1 + cosine) are normalized to preserve total label weight n.
    successes = n * math.fsum((1 + c) * y for c, y in zip(similarities, labels)) / (n + math.fsum(similarities))
    return (1 + successes) / (n + 2)


class PreparedEvidence:
    """Reusable local evaluation adapter; fit IDF only on this revealed prefix."""
    def __init__(self, vectors):
        self.n = len(vectors)
        df = Counter(term for vector in vectors for term in vector)
        self.default_idf = 1 + math.log(1 + self.n)
        self.idf = {term: 1 + math.log((1 + self.n) / (1 + count)) for term, count in df.items()}
        self.vectors = []
        for vector in vectors:
            weighted = {term: value * self.idf[term] for term, value in vector.items()}
            norm = math.sqrt(math.fsum(v*v for v in weighted.values()))
            self.vectors.append({k: v/norm for k, v in weighted.items()} if norm else {})

    def similarities(self, target):
        weighted = {term: value * self.idf.get(term, self.default_idf) for term, value in target.items()}
        norm = math.sqrt(math.fsum(v*v for v in weighted.values()))
        if not norm:
            return [0.] * self.n
        unit = {term: value/norm for term, value in weighted.items()}
        values = []
        for vector in self.vectors:
            small, large = (unit, vector) if len(unit) < len(vector) else (vector, unit)
            cosine = math.fsum(value * large.get(term, 0.) for term, value in small.items())
            values.append(min(1., max(0., cosine)))
        return values


def predict(input: list[dict], labeled: list | None = None) -> float:
    if not labeled:
        return 0.5
    subject, item = input
    benchmark = item.get('benchmark_id')
    if not isinstance(benchmark, str) or not benchmark:
        raise ValueError('Expected a nonempty benchmark ID')
    texts, labels = [], []
    for (other_subject, other_item), label in labeled or []:
        if other_subject != subject or other_item.get('benchmark_id') != benchmark:
            continue
        if label not in (0, 1):
            raise ValueError('Expected binary outcomes')
        texts.append(other_item.get('item_content', ''))
        labels.append(int(label))
    if len(labels) < 2:
        return float((1 + sum(labels)) / (len(labels) + 2))
    prepared = PreparedEvidence([features(text) for text in texts])
    similarities = prepared.similarities(features(item.get('item_content', '')))
    return float(weighted_prediction(similarities, labels))
