"""Signal collectors: arxiv + lightweight website scraping."""

from .arxiv import collect_arxiv
from .website import collect_website

__all__ = ["collect_arxiv", "collect_website"]
