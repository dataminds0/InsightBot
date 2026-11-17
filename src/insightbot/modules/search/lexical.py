"""Lexical keyword search engine with BM25 term weighting and safe snippet extraction."""


from insightbot.modules.deduplication.detector import normalize_text_for_dedup


def extract_search_tokens(query: str) -> list[str]:
    """Tokenize and normalize search query into meaningful terms."""
    norm = normalize_text_for_dedup(query)
    words = norm.split()
    # Filter very short trivial terms
    stopwords = {"في", "من", "على", "الى", "إلى", "عن", "مع", "in", "on", "at", "the", "a", "an", "в", "на", "с"}
    return [w for w in words if w not in stopwords and len(w) > 1]


def compute_lexical_score(tokens: list[str], title: str, text: str) -> tuple[float, str]:
    """
    Compute BM25-like lexical relevance score and generate safe snippet.
    Gives 2.5x boost to title occurrences.
    """
    if not tokens:
        return 0.0, ""

    norm_title = normalize_text_for_dedup(title)
    norm_text = normalize_text_for_dedup(text)

    score = 0.0
    first_match_idx = -1
    matched_term = ""

    for tok in tokens:
        # Title occurrences (boosted)
        t_count = norm_title.count(tok)
        if t_count > 0:
            score += 2.5 * (t_count / (t_count + 1.2))

        # Body text occurrences
        b_count = norm_text.count(tok)
        if b_count > 0:
            score += 1.0 * (b_count / (b_count + 1.2))
            if first_match_idx == -1:
                first_match_idx = text.lower().find(tok)
                matched_term = tok

    # Generate snippet (bounded to 150 characters around match)
    snippet = ""
    if first_match_idx != -1 and text:
        start = max(0, first_match_idx - 40)
        end = min(len(text), first_match_idx + len(matched_term) + 100)
        snip = text[start:end].strip()
        snippet = f"...{snip}..." if start > 0 else f"{snip}..."
    elif text:
        snippet = text[:150].strip() + "..."

    return round(score, 4), snippet
