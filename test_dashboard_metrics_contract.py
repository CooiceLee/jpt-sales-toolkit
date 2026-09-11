"""A number that can be followed leads to exactly the leads it counted.

The dashboard's counts are questions - "which 193?" - and the app already has
the lists that answer them. So the ones with an exact destination open it, and
the ones without stay plain: "last 7 days" has no list filtered by seven days,
and an amount is not a set of leads. A metric that looks clickable and lands on
a different set of rows is worse than one that never offered.

The other thing pinned here is the ticket. Two dashboard loads can be in the
air at once - opening the page while a refresh is still out - and without a
ticket the older answer draws last, which is how a failure message gets
replaced by numbers that are no longer true.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
LINKS = (ROOT / "frontend" / "js" / "modules"
         / "dashboard-links.js").read_text(encoding="utf-8")


def targets() -> dict[str, dict[str, str]]:
    block = LINKS[LINKS.index("const TARGETS"):LINKS.index("function target")]
    found = {}
    for key, body in re.findall(r"'([\w-]+)':\s*\{([^}]*)\}", block):
        entry = dict(re.findall(r"(\w+):\s*'([^']*)'", body))
        found[key] = entry
    return found


def check_only_metrics_with_a_list_are_clickable() -> None:
    linked = targets()
    assert linked, "no metric leads anywhere"
    for key in ("kpi-recent", "kpi-pipeline"):
        assert key not in linked, (
            f"{key} has no list holding exactly what it counts, so it must not "
            "look clickable"
        )
    # Every stage in the funnel is offered, or the reader learns the rows are
    # sometimes clickable and sometimes not for no visible reason.
    for stage in ("New", "Assigned", "Following", "Quoted", "Won", "Lost"):
        assert f"stage-{stage}" in linked, f"the {stage} row leads nowhere"


def check_every_destination_exists_with_that_filter() -> None:
    for key, where in targets().items():
        module = where.get("module")
        assert f'id="module-{module}"' in INDEX, f"{key}: no page {module}"
        block = INDEX[INDEX.index(f'id="module-{module}"'):]
        block = block[:block.index('id="module-', 20)] if 'id="module-' in block[20:] else block
        if "tab" in where:
            assert f'data-filter="{where["tab"]}"' in block, (
                f"{key}: {module} has no filter tab {where['tab']}"
            )
        if "stage" in where and where["stage"]:
            assert f'value="{where["stage"]}"' in block, (
                f"{key}: {module} has no stage option {where['stage']}"
            )


def check_a_drill_down_carries_no_other_filters() -> None:
    """The number counted every lead in that state; the list must too.

    The queues share a search, an owner, a technical owner, a customer and a
    region, and the follow-up page adds activity time. Left in place, "210
    inquiries" opened a list of four: the metric and the rows stopped
    describing the same thing.
    """
    for field in ("search", "ownerId", "techId", "customerId", "businessRegion"):
        assert f"State.stageFilters.{field} = ''" in LINKS, (
            f"a drill-down keeps the shared {field} filter, so the list it "
            "opens is not the leads the number counted"
        )
    assert "followup-activity-filter" in LINKS, (
        "the follow-up page's own activity-time filter survives the jump"
    )
    # And only after the reader has really left: cancelling an unsaved panel
    # must not wipe the filters they were working with.
    order = LINKS.index("switchModule") < LINKS.index("clearQueueFilters();\n        const module")
    assert order, "the filters are cleared before the page change is agreed to"


def check_one_stage_does_not_open_a_two_stage_list() -> None:
    """The follow-up queue is Assigned + Following by design.

    That is right for the module's own count and wrong for a single funnel
    stage: clicking "Following" opened a list that also held the assigned ones.
    """
    linked = targets()
    assert linked["kpi-following"]["module"] == "followup", (
        "the follow-up module count should open the follow-up queue"
    )
    single = linked["stage-Following"]
    assert single.get("stage") == "Following", (
        "the Following funnel row does not ask for exactly that stage: "
        f"{single}"
    )
    assert single["module"] != "followup", (
        "a single stage opens the two-stage queue, so the rows include Assigned"
    )
    loader = (ROOT / "frontend" / "js" / "modules"
              / "sales-worklists.js").read_text(encoding="utf-8")
    assert "['Assigned', 'Following'].includes(lead.sales_stage)" in loader, (
        "the follow-up queue no longer holds both stages, which changes a "
        "business rule this fix was not allowed to touch"
    )


def check_the_affordance_is_only_on_the_linked_ones() -> None:
    funnel = APP[APP.index("function renderFunnel"):]
    funnel = funnel[:funnel.index("\n}")]
    assert "DashboardLinks?.target?.(key)" in funnel, (
        "the funnel decides on its own which rows are clickable"
    )
    assert "linked ? " in funnel and 'role="button"' in funnel
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    # Three things a reader uses to tell them apart: the pointer, the hover,
    # and a focus ring for the keyboard.
    for rule in ("cursor: pointer", ":hover", ":focus-visible"):
        assert any(rule in line for line in css.splitlines()
                   if ".is-linked" in line), (
            f"a metric that opens a list has no {rule}, so it looks exactly "
            "like one that does not"
        )


def check_the_dashboard_answers_its_newest_request() -> None:
    load = APP[APP.index("async function loadDashboard"):]
    load = load[:load.index("\nfunction renderFunnel")]
    assert "WorklistRequest.begin('dashboard')" in load, (
        "the dashboard has no ticket, so an older answer can draw last"
    )
    assert load.count("WorklistRequest.isCurrent(request)") >= 3, (
        "the ticket is not checked after every wait that precedes a change"
    )
    order = INDEX.index("modules/worklist-request.js") < INDEX.index("js/app.js")
    assert order, "app.js runs before the module it takes tickets from"


def main() -> None:
    check_only_metrics_with_a_list_are_clickable()
    check_every_destination_exists_with_that_filter()
    check_a_drill_down_carries_no_other_filters()
    check_one_stage_does_not_open_a_two_stage_list()
    check_the_affordance_is_only_on_the_linked_ones()
    check_the_dashboard_answers_its_newest_request()
    print("PASS: dashboard metrics lead to the rows they counted, and the "
          "newest answer is the one on screen")


if __name__ == "__main__":
    main()
