"""A member's own departure day, and what happens when it falls outside the trip.

Somebody set a colleague's departure to a day before the trip began, nothing
moved, and nothing said why - so they set it again, and again, while the same
"cannot reach this visit" kept being reported.

The rule itself is right: a plan cannot begin before it begins, so a date
before the start is passed over and that member leaves with the team. Standing
silently about it was the mistake. Both ends of the window are now reported -
before the start and after the end - and the sentence says which day is being
used instead.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.services.trip_team_adapter import member_departure_slots

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"


class Core:
    """Only the two helpers the function asks of it."""

    @staticmethod
    def _parse_date(value):
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _slot_key(slot):
        return (slot[0].toordinal(), 0 if slot[1] == "AM" else 1)


class Members:
    def __init__(self, slots):
        self._slots = slots

    def departure_slots(self, plan_id):
        return self._slots


START = (date(2026, 9, 14), "AM")
END = date(2026, 10, 30)


def run(dates):
    return member_departure_slots(Core(), Members(dates), "p1", START, END)


def check_a_day_inside_the_window_is_used() -> None:
    slots, risks = run({"u1": "2026-09-20"})
    assert slots == {"u1": (date(2026, 9, 20), "AM")}, slots
    assert risks == [], risks


def check_a_day_before_the_start_is_reported_not_applied() -> None:
    slots, risks = run({"u1": "2026-09-10"})
    assert slots == {}, (
        "a departure before the trip began moved the schedule, so the trip "
        f"starts earlier than the plan says: {slots}"
    )
    assert len(risks) == 1, risks
    risk = risks[0]
    assert risk["kind"] == "member_departure_before_plan_start", risk
    assert risk["departure_date"] == "2026-09-10", risk
    assert risk["start_date"] == "2026-09-14", (
        "the report does not say which day is used instead, which is the one "
        f"thing the reader needs: {risk}"
    )


def check_a_day_after_the_end_is_still_reported() -> None:
    slots, risks = run({"u1": "2026-11-05"})
    assert slots == {}
    assert [risk["kind"] for risk in risks] == ["member_departure_after_plan_end"]


def check_the_first_day_of_the_trip_is_not_a_mistake() -> None:
    slots, risks = run({"u1": "2026-09-14"})
    assert slots == {}, "leaving on the first day is the same as leaving with the team"
    assert risks == [], (
        "leaving on the day the trip starts was reported as a problem: "
        f"{risks}"
    )


ROW_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

const ctx = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  document: { getElementById: () => null, addEventListener() {} },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-team-view.js', 'utf8'),
                ctx, { filename: 'trip-team-view.js' });

const plan = { start_date: '2026-09-14', end_date: '2026-10-30',
               origin_name: 'SZX', destination_name: 'PVG' };
const row = date => ctx.TripTeamView.renderMember(plan,
  { user_id: 'u1', display_name: 'Anna Berg', departure_date: date });

assert.match(row('2026-09-10'), /Before the trip starts on 2026-09-14/,
  'a departure before the trip starts is not mentioned on the field it was typed into');
assert.match(row('2026-11-05'), /After the trip ends on 2026-10-30/,
  'a departure after the trip ends is not mentioned on the field');
assert.ok(!/Before the trip starts|After the trip ends/.test(row('2026-09-20')),
  'a date inside the trip was reported as a problem');
assert.ok(!/Before the trip starts|After the trip ends/.test(row('')),
  'leaving with the team was reported as a problem');
assert.ok(!/Before the trip starts/.test(row('2026-09-14')),
  'leaving on the first day was reported as a problem');
console.log(JSON.stringify({ ok: true }));
"""


def check_the_field_says_it_where_it_was_typed() -> None:
    """A recalculation away is too late: the date was typed in the team card."""
    import json
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(ROW_HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"]
    risks = (MODULES / "trip-team-risks.js").read_text(encoding="utf-8")
    assert "member_departure_before_plan_start" in risks, (
        "the new report has no sentence, so it reaches the reader as nothing"
    )
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    assert "早于计划开始日" in i18n, "the field note is not translated"


def main() -> None:
    check_a_day_inside_the_window_is_used()
    check_a_day_before_the_start_is_reported_not_applied()
    check_a_day_after_the_end_is_still_reported()
    check_the_first_day_of_the_trip_is_not_a_mistake()
    check_the_field_says_it_where_it_was_typed()
    print("PASS: a departure day outside the trip is reported at both ends, and "
          "the schedule still starts when the plan starts")


if __name__ == "__main__":
    main()
