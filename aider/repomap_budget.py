"""Optional hard limit for rendered repository context, including its prefix."""
import os


def read_map_limit(value=None):
    if value is None:
        value = os.environ.get("AIDER_REPO_MAP_TOKEN_LIMIT")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("repo-map token limit must be a non-negative integer")
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise ValueError("repo-map token limit must be a non-negative integer") from None
    if str(limit) != str(value).strip() or limit < 0:
        raise ValueError("repo-map token limit must be a non-negative integer")
    return limit


def bound_map(prefix, listing, limit, count_tokens):
    """Keep a whole-line prefix of the listing; validate with the actual tokenizer.

    Ranking uses an estimate, so its nominal budget is not a hard ceiling.
    Binary search reduces tokenizer work. Every returned candidate is checked;
    token counts need not be monotonic, though nonmonotonicity may underfill.
    """
    text = prefix + listing
    tokens = count_tokens(text)
    if tokens <= limit:
        return text, tokens, False
    lines = listing.splitlines(keepends=True)
    low, high = 0, len(lines)
    best, best_tokens = "", 0
    while low <= high:
        mid = (low + high) // 2
        candidate = prefix + "".join(lines[:mid]) if mid else ""
        n = count_tokens(candidate) if candidate else 0
        if n <= limit:
            best, best_tokens = candidate, n
            low = mid + 1
        else:
            high = mid - 1
    return best, best_tokens, True
