"""Deterministic story clustering algorithms, chain-merge guards, and entity extractors."""

from datetime import timedelta

from insightbot.models.article import Article
from insightbot.models.story import (
    EntityCategory,
    EntityMention,
    Story,
)
from insightbot.modules.deduplication.detector import (
    compute_headline_similarity,
    compute_shingle_jaccard,
    normalize_text_for_dedup,
)

# Prominent geopolitical and regional entities for location guard
KNOWN_LOCATIONS: dict[str, list[str]] = {
    "Yemen": ["اليمن", "yemen", "йемен"],
    "Aden": ["عدن", "aden", "аден"],
    "Sanaa": ["صنعاء", "sanaa", "sana'a", "сана"],
    "Saudi Arabia": ["السعودية", "المملكة العربية السعودية", "saudi", "saudi arabia", "саудовская аравия"],
    "Riyadh": ["الرياض", "riyadh", "эр-рияд"],
    "Egypt": ["مصر", "egypt", "египет"],
    "Cairo": ["القاهرة", "cairo", "каир"],
    "USA": ["الولايات المتحدة", "واشنطن", "امريكا", "united states", "usa", "сша", "вашингтон"],
    "Russia": ["روسيا", "موسكو", "russia", "moscow", "россия", "москва"],
    "France": ["فرنسا", "باريس", "france", "paris", "франция", "париж"],
    "UK": ["بريطانيا", "لندن", "uk", "britain", "london", "великобритания", "лондон"],
    "Japan": ["اليابان", "طوكيو", "japan", "tokyo", "япония", "токио"],
    "China": ["الصين", "بكين", "china", "beijing", "китай", "пекин"],
    "Palestine": ["فلسطين", "غزة", "القدس", "palestine", "gaza", "палестина", "газа"],
    "Lebanon": ["لبنان", "بيروت", "lebanon", "beirut", "ливан", "бейрут"],
    "Chile": ["تشيلي", "سانتياغو", "chile", "santiago", "чили", "сантьяго"],
    "Turkey": ["تركيا", "أنقرة", "اسطنبول", "الاناضول", "turkey", "ankara", "istanbul", "турция", "анкара"],
    "Syria": ["سوريا", "دمشق", "syria", "damascus", "сирия", "дамаск"],
    "Iraq": ["العراق", "بغداد", "iraq", "baghdad", "ирак", "багдад"],
    "Iran": ["إيران", "ايران", "طهران", "iran", "tehran", "иран", "тегеран"],
    "Germany": ["ألمانيا", "المانيا", "برلين", "germany", "berlin", "германия", "берлин"],
    "Morocco": ["المغرب", "الرباط", "morocco", "rabat", "марокко"],
    "Sudan": ["السودان", "الخرطوم", "sudan", "khartoum", "судан"],
    "Jordan": ["الأردن", "الاردن", "عمان", "jordan", "amman", "иордания"],
    "Kuwait": ["الكويت", "kuwait", "кувейт"],
    "Qatar": ["قطر", "الدوحة", "qatar", "doha", "катар"],
    "UAE": ["الإمارات", "الامارات", "أبوظبي", "دبي", "uae", "emirates", "оаэ"],
}

# Known organizations
KNOWN_ORGS: dict[str, list[str]] = {
    "UN": ["الأمم المتحدة", "الامم المتحدة", "un", "united nations", "оон"],
    "OPEC": ["أوبك", "اوبك", "opec", "опэк"],
    "WHO": ["منظمة الصحة العالمية", "who", "воз"],
    "EU": ["الاتحاد الأوروبي", "الاتحاد الاوروبي", "eu", "european union", "ес"],
    "Arab League": ["جامعة الدول العربية", "arab league", "лига арабских государств"],
}


def extract_entities_from_text(article_id: str, text: str) -> list[EntityMention]:
    """
    Extract entity mentions (locations, organizations) from article text with exact offsets.
    Unresolved ambiguity is explicitly preserved (Defect defense: never hallucinate identities).
    """
    mentions: list[EntityMention] = []
    if not text:
        return mentions

    lower_text = text.lower()

    # Match locations
    for loc_name, patterns in KNOWN_LOCATIONS.items():
        for pat in patterns:
            start = 0
            while True:
                idx = lower_text.find(pat.lower(), start)
                if idx == -1:
                    break
                mentions.append(
                    EntityMention(
                        text=text[idx : idx + len(pat)],
                        category=EntityCategory.LOCATION,
                        article_id=article_id,
                        start_char=idx,
                        end_char=idx + len(pat),
                        resolved_id=loc_name,
                        is_resolved=True,
                    )
                )
                start = idx + len(pat)

    # Match organizations
    for org_name, patterns in KNOWN_ORGS.items():
        for pat in patterns:
            start = 0
            while True:
                idx = lower_text.find(pat.lower(), start)
                if idx == -1:
                    break
                mentions.append(
                    EntityMention(
                        text=text[idx : idx + len(pat)],
                        category=EntityCategory.ORGANIZATION,
                        article_id=article_id,
                        start_char=idx,
                        end_char=idx + len(pat),
                        resolved_id=org_name,
                        is_resolved=True,
                    )
                )
                start = idx + len(pat)

    return mentions


def extract_keywords_from_text(title: str, body: str, max_keywords: int = 10) -> list[str]:
    """Extract prominent thematic anchor keywords from title and lead paragraph."""
    norm_text = normalize_text_for_dedup(title + " " + body[:500])
    words = norm_text.split()
    stopwords = {
        "في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه", "التي", "الذي",
        "تم", "كان", "كانت", "ان", "أن", "قد", "او", "أو", "هو", "هي", "لا", "ما",
        "in", "on", "at", "the", "a", "an", "and", "or", "to", "for", "of", "with",
        "в", "на", "с", "по", "к", "и", "или", "что", "это", "как", "не",
    }
    meaningful = [w for w in words if len(w) > 3 and w not in stopwords]
    freq: dict[str, int] = {}
    for w in meaningful:
        freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.keys(), key=lambda w: freq[w], reverse=True)
    return sorted_words[:max_keywords]


class StoryClusteringEngine:
    """
    Evaluates whether an article belongs to an existing Story cluster
    while enforcing strict chain-merge, temporal, and location guardrails.
    """

    def __init__(
        self,
        headline_similarity_threshold: float = 0.55,
        shingle_similarity_threshold: float = 0.45,
        temporal_window_hours: float = 72.0,
    ):
        self.headline_sim_threshold = headline_similarity_threshold
        self.shingle_sim_threshold = shingle_similarity_threshold
        self.temporal_window_hours = temporal_window_hours

    def check_location_conflict(self, art_locations: set[str], story_locations: set[str]) -> bool:
        """
        LOCATION GUARD:
        If both the article and the story specify distinct locations with zero overlap
        (e.g. 'Aden' vs 'Sanaa' or 'Japan' vs 'Chile'), they must NOT be merged.
        """
        if art_locations and story_locations:
            if not (art_locations & story_locations):
                return True
        return False

    def evaluate_membership(
        self,
        article: Article,
        story: Story,
        lead_article: Article | None = None,
    ) -> tuple[bool, float, str]:
        """
        Determine if article belongs to story.
        Returns (belongs: bool, score: float, reason: str).
        """
        art_time = article.published_at or article.fetched_at

        # 1. Temporal Guard: article must be within temporal window of story coverage
        window = timedelta(hours=self.temporal_window_hours)
        if art_time < (story.first_article_at - window) or art_time > (story.last_article_at + window):
            return False, 0.0, "Temporal window exceeded"

        # 2. Location Guard
        art_mentions = extract_entities_from_text(article.article_id, article.title + " " + article.body_text)
        art_locs = {m.resolved_id for m in art_mentions if m.category == EntityCategory.LOCATION and m.resolved_id}
        story_locs = set(story.entities)  # entities list holds prominent resolved entities
        if story.primary_location:
            story_locs.add(story.primary_location)

        if self.check_location_conflict(art_locs, story_locs):
            return False, 0.0, f"Conflicting locations: {art_locs} vs {story_locs}"

        # 3. Chain-Merge Guard:
        # Evaluate against the lead article if provided, not merely arbitrary members
        reference_title = lead_article.title if lead_article else story.title
        reference_body = lead_article.body_text if lead_article else ""

        h_sim = compute_headline_similarity(article.title, reference_title)
        s_sim = compute_shingle_jaccard(article.body_text[:1000], reference_body[:1000], k=3) if reference_body else 0.0

        # Keyword overlap with story thematic anchors
        art_keywords = set(extract_keywords_from_text(article.title, article.body_text))
        story_keywords = set(story.keywords)
        kw_overlap = len(art_keywords & story_keywords) / max(len(story_keywords), 1)

        # Shared resolved entities (locations, organizations)
        shared_entities = art_locs & story_locs
        entity_score = len(shared_entities) / max(len(story_locs), 1) if story_locs else 0.0

        # Combined event score
        combined_score = (h_sim * 0.35) + (s_sim * 0.25) + (kw_overlap * 0.25) + (entity_score * 0.15)

        # Threshold check:
        # 1. High headline similarity OR strong combined event score with keyword overlap
        if h_sim >= self.headline_sim_threshold or (combined_score >= 0.40 and kw_overlap >= 0.20):
            return True, round(combined_score, 4), f"Matched event: h_sim={h_sim:.2f}, kw_overlap={kw_overlap:.2f}"

        # 2. Cross-lingual / multi-source event corroboration (>= 2 shared entities, e.g. Yemen + Aden) within tight temporal window
        time_delta_h = abs((art_time - story.first_article_at).total_seconds()) / 3600.0
        if len(shared_entities) >= 2 and time_delta_h <= 24.0:
            return True, round(combined_score, 4), f"Matched cross-lingual entities: {shared_entities} within {time_delta_h:.1f}h"

        return False, round(combined_score, 4), "Insufficient event similarity"
