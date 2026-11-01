"""Deterministic lexical duplicate audit using token-shingle Jaccard similarity."""
from collections import Counter, defaultdict
import math
import re
import unicodedata


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())


def shingles(text):
    tokens = re.findall(r"\w+|[^\w\s]", normalized(text))
    width = min(5, len(tokens))
    return {tuple(tokens[i:i + width]) for i in range(len(tokens) - width + 1)} if width else set()


def audit_items(records, threshold=.9):
    """Return cluster IDs and matched pairs, without using labels.

    Rare-shingle prefixes filter candidates; exact Jaccard confirms each match.
    Every qualifying pair must share at least one shingle in this prefix because
    overlap >= ceil(threshold * len(left)). Empty texts are rejected.
    """
    keys = sorted(records)
    texts = [normalized(records[k]) for k in keys]
    grams = [shingles(text) for text in texts]
    if any(not g for g in grams):
        raise ValueError("Empty items need an explicit duplicate policy")
    postings = defaultdict(list)
    for i, group in enumerate(grams):
        for gram in group:
            postings[gram].append(i)
    parents = list(range(len(keys)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    matches = []
    comparisons = 0
    for i, group in enumerate(grams):
        prefix_length = len(group) - math.ceil(threshold * len(group)) + 1
        prefix = sorted(group, key=lambda g: (len(postings[g]), g))[:prefix_length]
        candidates = {j for g in prefix for j in postings[g] if j > i}
        for j in sorted(candidates):
            other = grams[j]
            if min(len(group), len(other)) / max(len(group), len(other)) < threshold:
                continue
            comparisons += 1
            intersection = len(group & other)
            similarity = intersection / (len(group) + len(other) - intersection)
            if similarity >= threshold or texts[i] == texts[j]:
                a, b = root(i), root(j)
                parents[max(a, b)] = min(a, b)
                matches.append({"left": keys[i], "right": keys[j], "jaccard": similarity,
                                "normalized_exact": texts[i] == texts[j]})
    clusters = {key: keys[root(i)] for i, key in enumerate(keys)}
    counts = Counter(clusters.values())
    return clusters, {"threshold": threshold, "shingle_width": 5, "items": len(keys),
                      "candidate_comparisons": comparisons, "matched_pairs": len(matches),
                      "duplicate_clusters": sum(n > 1 for n in counts.values()),
                      "largest_cluster": max(counts.values()), "pairs": matches,
                      "scope": "Lexical overlap only; does not detect arbitrary paraphrases or semantic duplicates"}
