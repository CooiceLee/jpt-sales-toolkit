"""The candidate list in the narrow side column, at the widths people use.

The column is about a third of the width this table was drawn for, so it paid
for the same cell padding on every column twice over. The last column was
pushed past the container: its buttons landed outside the row divider, every
row ended somewhere different, and the lead id was broken across three lines -
at which point it stops being a reference anybody can read.

Columns are given their sizes here rather than left to fight over what is left,
and below the width where four of them fit, the city goes - it is the one thing
on this row the map beside it already shows - rather than the action, which is
the point of the list.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
MODULES = ROOT / "frontend" / "js" / "modules"


def rule(selector: str) -> str:
    """The declarations of the first rule with this exact selector text."""
    index = CSS.index(selector)
    return CSS[index:CSS.index("}", index)]


def check_the_columns_are_given_their_widths() -> None:
    block = rule(".trip-side #trip-candidate-list .data-table {\n    table-layout: fixed")
    assert "table-layout: fixed" in block, (
        "the columns are left to fight over the width again, so the row ends "
        "wherever the content happens to reach"
    )
    assert "min-width" in block, "nothing stops the columns being squeezed to nothing"
    # The score pill is 48px wide; a 44px column cut it on every row.
    score = rule(".trip-side #trip-candidate-list .data-table th:nth-child(3),")
    width = int(re.search(r"width:\s*(\d+)px", score).group(1))
    assert width >= 48, f"the score column is {width}px and the pill it holds is 48px"


def check_the_action_survives_the_narrow_column() -> None:
    actions = rule(".trip-side #trip-candidate-list .trip-candidate-actions {")
    assert "flex-direction: column" in actions, (
        "the two buttons sit side by side in a column too narrow for them, so "
        "they wrap raggedly and the second one leaves the cell"
    )
    assert "align-items: stretch" in actions, "the stacked buttons are different widths"
    assert "@media (min-width: 1201px) and (max-width: 1399px)" in CSS, (
        "below the width where four columns fit, nothing gives way - so the "
        "column that gives way is the one holding the button"
    )
    band = CSS[CSS.index("@media (min-width: 1201px) and (max-width: 1399px)"):]
    assert "nth-child(2)" in band[:600] and "display: none" in band[:600], (
        "the city column is not the one dropped in the narrow band"
    )


def check_the_lead_id_is_not_broken_apart() -> None:
    """JPT-2609-0021 down three lines is not a reference anybody can use."""
    assert ".trip-candidate-id" in CSS, "the lead id has no rules of its own"
    block = rule(".trip-candidate-id {")
    assert "white-space: nowrap" in block, "the id can be broken mid-token again"
    assert "text-overflow: ellipsis" in block, (
        "with nowrap and no ellipsis the id is simply cut off"
    )
    source = (MODULES / "trip-candidates-list.js").read_text(encoding="utf-8")
    assert 'class="trip-candidate-id"' in source, (
        "the id is styled inline again, so the rules above never reach it"
    )


def main() -> None:
    check_the_columns_are_given_their_widths()
    check_the_action_survives_the_narrow_column()
    check_the_lead_id_is_not_broken_apart()
    print("PASS: the candidate rows line up in the narrow column, the action "
          "stays in view, and the lead id stays in one piece")


if __name__ == "__main__":
    main()
