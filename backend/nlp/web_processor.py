import re
import socket
from urllib.parse import urlparse, urljoin
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup, Comment

class WebpageProcessor:
    """
    Intelligent Webpage Extractor & Sanitizer for FAQForge.
    Fetches remote web URLs, cleans boilerplate (navigation, scripts, ads, footers),
    extracts metadata (title, domain, description), and structures the content
    into heading-aware sections suitable for semantic chunking and FAQ generation.
    """

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 FAQForge/2.5"
    )

    FORBIDDEN_HOSTS = {
        "127.0.0.1", "localhost", "0.0.0.0", "::1",
        "169.254.169.254", "metadata.google.internal"
    }

    TAGS_TO_REMOVE = [
        "script", "style", "noscript", "nav", "header", "footer", "aside",
        "svg", "form", "iframe", "button", "input", "select", "textarea",
        "dialog", "template", "audio", "video", "canvas"
    ]

    NOISE_PATTERNS = [
        "cookie", "advertisement", "banner", "popup", "newsletter",
        "sidebar", "social-share", "subscribe", "widget", "disclaimer"
    ]

    @classmethod
    def validate_url(cls, raw_url: str) -> str:
        """Normalizes and validates a given URL string."""
        url = raw_url.strip()
        if not url:
            raise ValueError("URL cannot be empty.")

        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError(f"Invalid URL format: '{raw_url}'. Please provide a valid domain (e.g. https://example.com).")

        hostname = parsed.hostname.lower() if parsed.hostname else ""
        if hostname in cls.FORBIDDEN_HOSTS or hostname.startswith("192.168.") or hostname.startswith("10."):
            raise ValueError(f"Access to private/internal host '{hostname}' is not permitted for security.")

        return url

    @classmethod
    def fetch_url(cls, url: str, timeout: int = 15) -> requests.Response:
        """Fetches the webpage with proper HTTP headers and redirect handling."""
        valid_url = cls.validate_url(url)
        headers = {
            "User-Agent": cls.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }

        try:
            resp = requests.get(valid_url, headers=headers, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            
            # Content-type check
            content_type = resp.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type and "text/plain" not in content_type:
                raise ValueError(
                    f"Unsupported content type '{content_type}'. FAQForge URL analyzer supports HTML webpages and articles."
                )
            
            return resp
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request to '{url}' timed out after {timeout} seconds. The server took too long to respond.")
        except requests.exceptions.SSLError as e:
            raise ConnectionError(f"SSL/TLS Certificate verification failed for '{url}': {str(e)}")
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "Unknown"
            raise ConnectionError(f"Remote server returned HTTP error {code} for '{url}'.")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Could not connect to '{url}': {str(e)}")

    @classmethod
    def extract_from_url(cls, raw_url: str, timeout: int = 15) -> Dict[str, Any]:
        """
        Fetches and parses a webpage, returning a structured document dictionary
        compatible with FAQForge's NLPPipeline, DocumentChunker, and SourceVerifier.
        """
        valid_url = cls.validate_url(raw_url)
        resp = cls.fetch_url(valid_url, timeout=timeout)
        
        # Determine encoding
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        try:
            html = resp.content.decode(encoding, errors="replace")
        except Exception:
            html = resp.text

        return cls.parse_html(html, source_url=valid_url)

    @classmethod
    def parse_html(cls, html: str, source_url: str = "") -> Dict[str, Any]:
        """
        Parses raw HTML string into structured, heading-aware document representation.
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract metadata
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        
        # OpenGraph title fallback
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
                
        # Domain parsing
        domain = ""
        if source_url:
            domain = urlparse(source_url).netloc
        if not title and domain:
            title = f"Webpage from {domain}"
        elif not title:
            title = "Imported Webpage"

        # Description
        description = ""
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)}) or \
                    soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

        # 2. Strip comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 3. Strip noisy tags
        for tag_name in cls.TAGS_TO_REMOVE:
            for el in soup.find_all(tag_name):
                el.decompose()

        # Strip elements matching class/id noise patterns (e.g. cookie notices, sidebars)
        for noise in cls.NOISE_PATTERNS:
            for el in soup.find_all(attrs={"class": re.compile(noise, re.I)}):
                el.decompose()
            for el in soup.find_all(attrs={"id": re.compile(noise, re.I)}):
                el.decompose()

        # 4. Target primary content container if present
        content_root = (
            soup.find("article") or
            soup.find("main") or
            soup.find("div", attrs={"role": "main"}) or
            soup.find("div", attrs={"id": re.compile(r"content|main|article|body", re.I)}) or
            soup.body or
            soup
        )

        # 5. Extract hierarchical sections based on headings
        sections: List[Dict[str, Any]] = []
        all_headings: List[str] = []
        
        current_heading = title or "Introduction"
        current_paragraphs: List[str] = []

        # Find all meaningful text elements
        elements = content_root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre"])

        for el in elements:
            text = re.sub(r'\s+', ' ', el.get_text()).strip()
            if not text:
                continue

            if el.name in ["h1", "h2", "h3", "h4"]:
                # Finalize previous section if it has text
                if current_paragraphs:
                    section_text = "\n\n".join(current_paragraphs).strip()
                    if len(section_text.split()) >= 15:  # meaningful content threshold
                        sections.append({
                            "heading": current_heading,
                            "text": section_text,
                            "word_count": len(section_text.split())
                        })
                    current_paragraphs = []

                current_heading = text
                if text not in all_headings:
                    all_headings.append(text)
            else:
                # Regular paragraph / list item / blockquote
                # Avoid tiny noise items
                if len(text) > 20 or el.name in ["p", "blockquote"]:
                    current_paragraphs.append(text)

        # Append final section
        if current_paragraphs:
            section_text = "\n\n".join(current_paragraphs).strip()
            if section_text:
                sections.append({
                    "heading": current_heading,
                    "text": section_text,
                    "word_count": len(section_text.split())
                })

        # Fallback if no sections were extracted cleanly
        if not sections:
            raw_text = content_root.get_text(separator="\n\n", strip=True)
            clean_text = re.sub(r'\n{3,}', '\n\n', raw_text)
            if clean_text:
                sections.append({
                    "heading": title,
                    "text": clean_text,
                    "word_count": len(clean_text.split())
                })

        # 6. Format pages array matching DocumentProcessor contract
        pages_data = []
        unified_paragraphs = []

        for idx, sec in enumerate(sections, 1):
            sec_heading = sec["heading"]
            sec_text = sec["text"]
            unified_paragraphs.append(f"## {sec_heading}\n{sec_text}")
            
            pages_data.append({
                "page_number": idx,
                "text": sec_text,
                "headings": [sec_heading],
                "word_count": sec["word_count"],
                "is_empty": False,
                "is_scanned": False,
                "image_count": 0
            })

        full_text = "\n\n".join(unified_paragraphs).strip()
        total_words = sum(p["word_count"] for p in pages_data)

        if total_words < 20:
            raise ValueError(
                f"The webpage '{source_url or title}' yielded insufficient text ({total_words} words). "
                "The site may be protected, login-walled, or relies on client-side JavaScript rendering."
            )

        return {
            "text": full_text,
            "pages": pages_data,
            "total_pages": len(pages_data),
            "scanned_pages_count": 0,
            "headings": all_headings,
            "metadata": {
                "title": title,
                "url": source_url,
                "domain": domain,
                "description": description,
                "section_count": len(sections),
                "total_words": total_words
            },
            "file_type": "url"
        }
