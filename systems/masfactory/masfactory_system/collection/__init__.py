"""Signal collectors: arxiv + lightweight website scraping + Google News RSS."""

from .arxiv import collect_arxiv
from .news import collect_google_news
from .website import collect_website

__all__ = ["collect_arxiv", "collect_google_news", "collect_website"]
