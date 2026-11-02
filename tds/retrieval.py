"""BM25 retrieval over the knowledge base (pure Python, no vector DB).

With 23 chunks you could put everything in the prompt; retrieval is kept so
the design scales to the full Act plus circulars, and so each answer records
exactly which source passages the model was shown.
"""
import hashlib
import json
import math
import re
from collections import Counter
from functools import lru_cache

from .config import KB_PATH

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = set("a an the of for to and or in on by with from at as is are be this that any other than per".split())


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


@lru_cache(maxsize=1)
def load_kb() -> dict:
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))
    kb["_hash"] = hashlib.sha256(KB_PATH.read_bytes()).hexdigest()[:12]
    kb["_by_id"] = {c["id"]: c for c in kb["chunks"]}
    return kb


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(map(len, docs)) / len(docs)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, query: list[str], i: int) -> float:
        tf, dl = self.tf[i], len(self.docs[i])
        s = 0.0
        for t in query:
            if t in tf:
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s


@lru_cache(maxsize=1)
def _index() -> BM25:
    kb = load_kb()
    return BM25([tokenize(c["title"] + " " + c["text"]) for c in kb["chunks"]])


def retrieve(query: str, k: int, pinned_ids: list[str] = ()) -> list[dict]:
    """BM25 top-k, plus `pinned_ids` that are always included.

    Lexical search alone can miss the statutory definition of the right section
    (e.g. a software AMC query matches no 194C/194J wording), so the pipeline pins
    the core definition of every in-scope section: the model always sees the
    full menu of options, and retrieval only adds the specific circulars/practice.
    """
    kb = load_kb()
    q = tokenize(query)
    idx = _index()
    scores = {c["id"]: idx.score(q, i) for i, c in enumerate(kb["chunks"])}
    top = [cid for cid, s in sorted(scores.items(), key=lambda x: -x[1])[:k] if s > 0]
    out = []
    for cid in list(dict.fromkeys(top + list(pinned_ids))):
        c = kb["_by_id"][cid]
        out.append(dict(c, score=round(scores[cid], 3), pinned=cid not in top))
    return out


def core_definition_ids(rule_set: dict) -> list[str]:
    ids = [ref for spec in rule_set["sections"].values() for ref in spec["kb_refs"]]
    return list(dict.fromkeys(ids + ["kb-goods", "kb-out-of-scope"]))
