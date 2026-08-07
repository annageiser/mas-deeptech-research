# Appendix C — Ideal reference architecture: component-to-source mapping

Every architectural component listed in the ideal reference architecture (§2.1.5) traces to an external
published source, not to a system output. This is the anti-circularity evidence §5 asks for: the mapping
was drawn from the literature *before* either System A or System B produced results, so the yardstick
is not derived from what was built. The table below lists each component with its primary published
source, a short justification, and where the component appears in the thesis or the codebase.

| Component | Requirement | Primary source | Justification (short) | Used in |
|---|---|---|---|---|
| Retrieval agent role | R1 · separation of roles | Liu et al. (2026), 'Agentic Collaboration on Explicit Graphs' | Nodes host agents/tools; edges carry dependencies + messages | §2.1.5 · docs/ideal-reference-architecture.md |
| Classification agent role (Ehrenthal four-signal scheme) | R1 · separation of roles + domain schema | Ehrenthal, Gonzalez-Padron & Gruen (2026) | Four-signal scheme + 19 sub-dimensions used verbatim | systems/masfactory/masfactory_system/classification/schema.yaml v0.4.2 |
| Reasoning agent role (patterns across actors and over time) | R1 · separation of roles | Liu et al. (2026); Wang et al. (2026) | Distinct reasoning role required by the graph; multi-path failure at depth motivates its distinctness | §2.1.5 |
| Verification agent role | R3 · verification stage | Kolbe & Burnett (1991); Wu et al. (2026, LogicGraph) | Reliability requirement carries from human coding to machine coding; multi-path proof coverage falls without a verifier | §2.1.5 · System A's Critic node |
| Traceability of every classified item to the role that produced it | R1 · separation of roles (derived) | Kolbe & Burnett (1991); Shaw (2001) | Content-analysis reliability + Shaw's structure-answers-requirements principle | §2.1.5 · System A per-node audit |
| Explicit collaboration graph (nodes + edges) | R1 · separation of roles | Liu et al. (2026) | Nodes host agents/tools; edges carry dependencies + messages | §2.1.5 |
| Persistent memory / shared context beneath the agents | R2 · persistent layer | Li et al. (2026a, AgentOS) | Shared context + memory placed beneath the agents | §2.1.5 · System B's Hermes memory |
| Reusable skills (compiled recurring task patterns) | R2 · persistent layer | Li et al. (2026b, OpenSage) | Recurring task patterns compiled into reusable skills | §2.1.5 · Hermes SKILL.md files |
| Extended tool use in the model itself | R2 · persistent layer (enabler) | Teknium et al. (2025) | Model trained for extended tool use, prerequisite for skill+memory stacks | §2.1.5 |
| Structured knowledge graph (actor ↔ signal ↔ category) | R3 · structured representation | Wu et al. (2026); Stewart & Buehler (2026); Adner (2017) | Multi-path proof structure + higher-order knowledge representation; Adner's activities/actors/positions/links | §2.1.5 · UNBUILT in both systems (§4.2 largest gap) |
| Architecture-as-characterisation stance (benchmark, not blueprint) | meta · validation type | Shaw (2001) | Pairs question type with the validation it requires; §2.1.5 is a characterisation, tested afterwards in §4.2 | §2.1.5 framing paragraph |

**Anti-circularity note.** No row in this table cites a system output. Rows whose 'Used in' column
names System A or System B name only *whether that component was implemented*, not the source of the
requirement itself. The gap analysis in §4.2 compares the implementations against this table; the
comparison is therefore between built systems and a literature-derived yardstick, not between
built systems and each other.
