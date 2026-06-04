"""Tests for the arXiv collector's author-affiliation gate (v0.4.1).

The bug being fixed: an arXiv paper that *mentions* an actor (in
references, acknowledgments, or compared-against-work) was being
attributed to that actor as a `publications` signal. Fix: parse the
`<arxiv:affiliation>` tag on each author and drop entries where no
author's affiliation matches the actor.

These tests use synthetic Atom XML strings — no network, no feedparser
HTTP — so they pin the parse / match logic deterministically.
"""

from __future__ import annotations

from masfactory_system.collection.arxiv import (
    _parse_affiliations_by_id,
    _actor_needles,
    _matches_actor,
    _belongs_to_actor,
)
from masfactory_system.schema import Actor


def _first_id_and_affs(xml: str) -> tuple[str, list[str]]:
    """Helper — parse the XML, return (entry_id, affiliations) for the 1st entry."""
    by_id = _parse_affiliations_by_id(xml)
    assert by_id, "expected ≥ 1 entry in test XML"
    eid = next(iter(by_id))
    return eid, by_id[eid]


SAMPLE_PAPER_WITH_AFFILIATION = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2606.12345v1</id>
    <title>Quantum error correction at scale</title>
    <summary>We demonstrate a new approach to QEC ...</summary>
    <link href="http://arxiv.org/abs/2606.12345v1"/>
    <author>
      <name>Alice Researcher</name>
      <arxiv:affiliation>ETH Zurich</arxiv:affiliation>
    </author>
    <author>
      <name>Bob Coauthor</name>
      <arxiv:affiliation>EPFL</arxiv:affiliation>
    </author>
  </entry>
</feed>"""


PAPER_THAT_ONLY_CITES_ETH = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2606.99999v1</id>
    <title>Survey of quantum approaches</title>
    <summary>We compare against the ETH Zurich superconducting platform ...</summary>
    <link href="http://arxiv.org/abs/2606.99999v1"/>
    <author>
      <name>Charlie Author</name>
      <arxiv:affiliation>MIT</arxiv:affiliation>
    </author>
    <author>
      <name>Dana Coauthor</name>
      <arxiv:affiliation>Stanford University</arxiv:affiliation>
    </author>
  </entry>
</feed>"""


PAPER_WITH_NO_AFFILIATION = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/0901.0001v1</id>
    <title>An ETH Zurich quantum prototype</title>
    <summary>The ETH Zurich team report a 2-qubit demonstration ...</summary>
    <link href="http://arxiv.org/abs/0901.0001v1"/>
    <author><name>Eve Older</name></author>
  </entry>
</feed>"""


PAPER_NO_AFF_NO_MENTION = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/0901.0002v1</id>
    <title>Generic quantum overview</title>
    <summary>We review the field broadly ...</summary>
    <link href="http://arxiv.org/abs/0901.0002v1"/>
    <author><name>Fran Anonymous</name></author>
  </entry>
</feed>"""


def _eth() -> Actor:
    return Actor(
        slug="eth-zurich",
        name="ETH Zurich",
        category="university_or_research_hub",
        aliases=["ETHZ", "ETH Zürich", "Eidgenössische Technische Hochschule"],
    )


# ---------- pure helpers ----------

def test_parse_affiliations_extracts_per_entry() -> None:
    by_id = _parse_affiliations_by_id(SAMPLE_PAPER_WITH_AFFILIATION)
    assert len(by_id) == 1
    affs = next(iter(by_id.values()))
    assert "ETH Zurich" in affs
    assert "EPFL" in affs


def test_parse_affiliations_empty_for_paper_without_tags() -> None:
    by_id = _parse_affiliations_by_id(PAPER_WITH_NO_AFFILIATION)
    assert next(iter(by_id.values())) == []


def test_actor_needles_includes_name_and_aliases() -> None:
    needles = _actor_needles(_eth())
    assert "eth zurich" in needles
    assert "ethz" in needles
    assert "eidgenössische technische hochschule" in needles


def test_matches_actor_is_case_insensitive_substring() -> None:
    needles = ["epfl"]
    assert _matches_actor(needles, "EPFL-LQM Quantum Lab") is True
    assert _matches_actor(needles, "Mit Csail") is False


# ---------- the headline decision ----------

def _decide(xml: str, actor: Actor, title: str = "", summary: str = "") -> tuple[bool, str]:
    _eid, affs = _first_id_and_affs(xml)
    # If the test didn't override title/summary, parse them out of the XML.
    if not (title or summary):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        ns = "{http://www.w3.org/2005/Atom}"
        entry = root.find(f"{ns}entry")
        title = (entry.findtext(f"{ns}title") or "").strip()
        summary = (entry.findtext(f"{ns}summary") or "").strip()
    return _belongs_to_actor(
        affiliations=affs, title=title, summary=summary, actor=actor
    )


def test_belongs_keeps_paper_with_matching_affiliation() -> None:
    keep, reason = _decide(SAMPLE_PAPER_WITH_AFFILIATION, _eth())
    assert keep is True
    assert "ETH Zurich" in reason


def test_belongs_drops_paper_that_only_cites_actor() -> None:
    """Bug fix: paper mentions ETH in abstract / body but no author lists
    ETH as affiliation → dropped."""
    keep, reason = _decide(PAPER_THAT_ONLY_CITES_ETH, _eth())
    assert keep is False
    assert "no author affiliation matches" in reason


def test_belongs_softfallback_when_no_affiliation_tags() -> None:
    """Older papers lacking affiliation tags → fall back to title/abstract."""
    keep, reason = _decide(PAPER_WITH_NO_AFFILIATION, _eth())
    assert keep is True
    assert "no affiliation tags" in reason


def test_belongs_drops_when_no_affs_and_no_body_mention() -> None:
    keep, _ = _decide(PAPER_NO_AFF_NO_MENTION, _eth())
    assert keep is False


def test_alias_fuzzy_matches_german_name() -> None:
    """An affiliation string with the umlaut version still matches via aliases."""
    paper = SAMPLE_PAPER_WITH_AFFILIATION.replace(
        "<arxiv:affiliation>ETH Zurich</arxiv:affiliation>",
        "<arxiv:affiliation>ETH Zürich</arxiv:affiliation>",
    )
    keep, _ = _decide(paper, _eth())
    assert keep is True


def test_drops_when_only_unrelated_affiliations() -> None:
    keep, _ = _decide(PAPER_THAT_ONLY_CITES_ETH, _eth())
    assert keep is False


def test_no_aliases_still_works_with_just_name() -> None:
    actor = Actor(slug="eth-zurich", name="ETH Zurich",
                  category="university_or_research_hub")
    keep, _ = _decide(SAMPLE_PAPER_WITH_AFFILIATION, actor)
    assert keep is True
