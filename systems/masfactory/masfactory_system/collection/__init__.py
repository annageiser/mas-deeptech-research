"""Signal collectors: arxiv + lightweight website scraping + Google News RSS + press-release aggregator + EPO patents (swissreg)."""

from .arxiv import collect_arxiv
from .news import collect_google_news
from .patents import collect_patents
from .press import collect_press_releases
from .website import collect_website

__all__ = [
    "collect_arxiv",
    "collect_google_news",
    "collect_patents",
    "collect_press_releases",
    "collect_website",
]
