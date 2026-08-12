"""The Examiner — the landman is the model, not the code.

Everything under this package obeys one rule: **no decision in Python**. If a
line of code chooses, compares, computes, filters or approves, it does not
belong here. Python opens files, turns pages into text or pixels, carries
messages to and from the model, and saves bytes. Pen and desk, not examiner.

The rule is not aesthetic. Twelve rounds of hardening produced twenty modules,
each born of one defect and none covering the next one. The bet here is that
judgement generalises where rules do not — so the judgement moves to the model
and the code stops having opinions.

What that costs: every gate, vocabulary and formula that used to guarantee a
property now has to be earned by the model each run, and checked by another
model rather than by an `if`. What it buys is measured, not assumed — round 1
produces a number against the current 1,178 evidenced cells and against the
hand-built DDR.
"""
