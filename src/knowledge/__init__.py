"""OKF — the knowledge layer (L0–L3) that governs categorisation.

`knowledge/` holds what is REUSABLE across units: the ontology and identity
keys (L0), the taxonomy (L1), the decision rules and closed vocabularies (L2),
and the lessons (L3). Unit FACTS never live here — they live in
`data/units/<UNIT>/` (invariant 13, enforced by the linter in this package).

The layer declares and constrains; it never classifies on its own. It gives the
AI the menu of candidates, the binary tests and the closed set of valid
answers; the AI reads content and proposes with a citation; the human arbitrates
by risk. A rule file that starts deciding by itself is a regex with a new badge.
"""
