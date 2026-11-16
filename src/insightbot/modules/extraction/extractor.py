"""Article content and metadata extractor utilizing local Trafilatura and htmldate."""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import dateparser
import htmldate
import trafilatura
from bs4 import BeautifulSoup

from insightbot.modules.extraction.models import ExtractedArticle

logger = logging.getLogger(__name__)

SITE_BRAND_SUFFIX_RE = re.compile(
    r"\s+[|\-–—]\s+(?:الجزيرة(?:\s+نت)?|BBC(?:\s+News)?(?:\s+عربي)?|العربية|سكاي نيوز عربية|Reuters|The Guardian|TASS|CNN|News).*$",
    flags=re.IGNORECASE,
)


class ArticleExtractor:
    """Extracts clean article body, full titles, and publication dates without truncating text."""

    def clean_title(self, raw_title: str, sitename: Optional[str] = None) -> str:
        """
        Clean title by stripping trailing publisher branding while strictly preserving
        meaningful punctuation (colons, semicolons, quotes, hyphens within headlines).
        Never truncates at colons.
        """
        if not raw_title:
            return ""

        title = " ".join(raw_title.strip().split())

        # Strip specific sitename branding at the end if present
        if sitename and len(sitename) > 2:
            escaped_site = re.escape(sitename.strip())
            title = re.sub(rf"\s+[|\-–—]\s+{escaped_site}$", "", title, flags=re.IGNORECASE)

        # Strip general known publisher branding suffixes
        title = SITE_BRAND_SUFFIX_RE.sub("", title)
        return title.strip()

    def parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse arbitrary date string into UTC datetime."""
        if not date_str:
            return None

        try:
            # First try ISO parse
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

        # Use dateparser for flexible localized parsing
        try:
            parsed = dateparser.parse(
                date_str, settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
            )
            if isinstance(parsed, datetime):
                return parsed.astimezone(timezone.utc)
        except Exception:
            pass

        return None

    def extract_from_html(
        self,
        html_content: str,
        url: str,
        fallback_title: Optional[str] = None,
        fallback_date: Optional[datetime] = None,
        language: str = "ar",
    ) -> ExtractedArticle:
        """
        Extract full title, body text, and publication date from raw HTML.
        Guarantees that Arabic colon titles survive, full text is preserved, and missing dates stay None.
        """
        if not html_content or not html_content.strip():
            return ExtractedArticle(
                title=fallback_title or "",
                body_text="",
                published_at=fallback_date,
                publication_date_unknown_reason="empty_html_document"
                if not fallback_date
                else None,
                language=language,
                quarantine_reason="empty_html_document",
            )

        # 1. Extract Trafilatura Document Metadata
        metadata = trafilatura.extract_metadata(html_content, default_url=url)

        # 2. Extract Main Content Body
        extracted_body = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True,
            include_images=False,
            include_links=False,
            output_format="txt",
        )

        # Fallback body extraction using BeautifulSoup if Trafilatura missed content
        if not extracted_body or len(extracted_body.strip()) < 50:
            soup = BeautifulSoup(html_content, "html.parser")
            # Remove scripts, styles, navigation, footer
            for el in soup(["script", "style", "nav", "footer", "header", "aside"]):
                el.decompose()

            article_tag = soup.find("article") or soup.find("main") or soup.body
            if article_tag:
                paragraphs = [
                    p.get_text(strip=True)
                    for p in article_tag.find_all("p")
                    if len(p.get_text(strip=True)) > 20
                ]
                if paragraphs:
                    extracted_body = "\n\n".join(paragraphs)

        body_text = (extracted_body or "").strip()

        # 3. Resolve Title (Preserving colons and meaningful punctuation)
        raw_title = ""
        sitename: Optional[str] = None

        if metadata:
            raw_title = metadata.title or ""
            sitename = metadata.sitename

        if not raw_title:
            soup = BeautifulSoup(html_content, "html.parser")
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                raw_title = h1.get_text(strip=True)
            elif soup.title and soup.title.get_text(strip=True):
                raw_title = soup.title.get_text(strip=True)
            elif fallback_title:
                raw_title = fallback_title

        final_title = self.clean_title(raw_title, sitename=sitename)

        # 4. Resolve Publication Date
        published_at: Optional[datetime] = None
        date_unknown_reason: Optional[str] = None

        # Try metadata date
        if metadata and metadata.date:
            published_at = self.parse_datetime(metadata.date)

        # Try htmldate discovery if metadata date was missing or unparseable
        if not published_at:
            try:
                discovered_date_str = htmldate.find_date(html_content, url=url)
                if discovered_date_str:
                    published_at = self.parse_datetime(discovered_date_str)
            except Exception:
                pass

        # Try fallback date from RSS entry
        if not published_at and fallback_date:
            published_at = fallback_date

        if not published_at:
            date_unknown_reason = "missing_in_feed_and_metadata"

        # 5. Language Resolution
        detected_language: Optional[str] = None
        if metadata and metadata.language:
            detected_language = metadata.language

        if not detected_language:
            soup = BeautifulSoup(html_content, "html.parser")
            html_tag = soup.find("html")
            if html_tag and html_tag.get("lang"):
                lang_val = str(html_tag["lang"]).split("-")[0].strip().lower()
                if lang_val:
                    detected_language = lang_val

        final_language = detected_language or language

        # 6. Quarantine Evaluation
        quarantine_reason: Optional[str] = None
        if not body_text or len(body_text) < 50:
            quarantine_reason = "insufficient_extracted_text"
        elif not final_title:
            quarantine_reason = "missing_article_title"

        # Metadata dictionary
        raw_meta = {}
        if metadata:
            raw_meta = {
                "author": metadata.author,
                "sitename": metadata.sitename,
                "description": metadata.description,
                "categories": metadata.categories,
                "tags": metadata.tags,
            }

        return ExtractedArticle(
            title=final_title,
            body_text=body_text,
            published_at=published_at,
            publication_date_unknown_reason=date_unknown_reason,
            author=metadata.author if metadata else None,
            language=final_language,
            quarantine_reason=quarantine_reason,
            raw_metadata=raw_meta,
        )
