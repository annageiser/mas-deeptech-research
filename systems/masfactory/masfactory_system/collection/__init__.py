"""Signal collectors: arxiv + lightweight website scraping + Google News RSS + press-release aggregator."""

from .arxiv import collect_arxiv
from .news import collect_google_news
from .press import collect_press_releases
from .website import collect_website

__all__ = [
    "collect_arxiv",
    "collect_google_news",
    "collect_press_releases",
    "collect_website",
]
