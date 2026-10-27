import re
from collections import defaultdict

ALIASES = {
    "Chinyere Elizabeth Utomi": [
        "chinyere",
        "chinyere utomi",
        "chinyere u",
        "chinyere elizabeth utomi",
    ],
}

SHARED_MARKERS = ("/", " and ", " & ", ",")

_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")


def normalise(raw):
    if not raw:
        return ""
    text = _PUNCT.sub(" ", raw.lower())
    words = _SPACE.sub(" ", text).strip().split()
    return " ".join(sorted(words))


def is_shared(raw):
    if not raw:
        return False
    return any(marker in raw.lower() for marker in SHARED_MARKERS)


def _alias_index():
    index = {}
    for canonical, keys in ALIASES.items():
        index[normalise(canonical)] = canonical
        for key in keys:
            index[normalise(key)] = canonical
    return index


_INDEX = _alias_index()


def canonical(raw):
    if not raw or not raw.strip():
        return "(unassigned)"
    if is_shared(raw):
        return f"(shared) {raw.strip()}"
    key = normalise(raw)
    if key in _INDEX:
        return _INDEX[key]
    return " ".join(word.capitalize() for word in raw.split())


def group_by_officer(rows, name_key="account_officer"):
    grouped = defaultdict(lambda: {"count": 0, "value": 0, "variants": {}})
    for row in rows:
        raw = row.get(name_key)
        name = canonical(raw)
        bucket = grouped[name]
        bucket["count"] += row.get("count", 0)
        bucket["value"] += row.get("value", 0) or 0
        if raw:
            bucket["variants"][raw] = row.get("count", 0)
    return dict(grouped)
