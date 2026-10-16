"""Extract and normalize text from fetched bytes."""
import io
import re
import unicodedata

from bs4 import BeautifulSoup

BLOCK_PAGE_MARKERS = ("access denied", "captcha", "are you a robot", "enable javascript to continue",
                      "request blocked", "403 forbidden")


def extract_text(content: bytes, content_type: str) -> str:
    if content_type == "application/pdf" or content[:5] == b"%PDF-":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        # page markers let evidence point at a page number
        return "\n".join(f"[page {i + 1}]\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages))
    if content_type == "text/plain":
        return content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg"]):
        tag.decompose()
    return soup.get_text("\n")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def validate_text(text: str) -> list[str]:
    """Return problems that make the document unusable as evidence. Empty list = OK."""
    problems = []
    if len(text) < 200:
        problems.append(f"too little text extracted ({len(text)} chars)")
    head = text[:2000].lower()
    for m in BLOCK_PAGE_MARKERS:
        if m in head and len(text) < 3000:
            problems.append(f"looks like a block/challenge page ('{m}')")
            break
    return problems
