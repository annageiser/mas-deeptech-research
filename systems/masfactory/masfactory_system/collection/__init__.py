"""Signal collectors: arxiv + lightweight website scraping + Google News RSS + press-release aggregator + EPO patents (swissreg) + central RSS feed registry."""

from .arxiv import collect_arxiv
from .news import collect_google_news
from .patents import collect_patents
from .press import collect_press_releases
from .rss import collect_rss_for_actors, load_feed_config
from .website import collect_website
from .websearch import collect_websearch

__all__ = [
    "collect_arxiv",
    "collect_google_news",
    "collect_patents",
    "collect_press_releases",
    "collect_rss_for_actors",
    "collect_website",
    "collect_websearch",
    "load_feed_config",
]
