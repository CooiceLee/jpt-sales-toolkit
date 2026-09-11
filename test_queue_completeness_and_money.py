"""A queue must show everything in it, and a total must say what it is in.

Two things a reader acts on directly were wrong. A hundred-and-five tasks came
back as the hundred on the first page, and the five customers they belonged to
came back as the one customer that page happened to cover - the navigation
number said five while the list showed one card. And amounts in different
currencies were added into a single figure that was then printed with a dollar
sign, so four deals of 10,000 EUR read as forty thousand dollars.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_queue_money_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import create_app  # noqa: E402
from backend.repositories import (  # noqa: E402
    AfterSalesTaskRepository,
    CustomerRepository,
    LeadRepository,
    UserCredentialRepository,
    UserRepository,
    close_db,
)
from backend.services.money_totals import (  # noqa: E402
    UNSPECIFIED,
    phrase,
    totals_by_currency,
)

PASSWORD = "QueueMoney2026!"
# More than one page, spread over several customers, so a single page can never
# stand for the whole queue.
TASK_COUNT = 105
LEAD_COUNT = 5


def expect(response, status: int, label: str):
    assert response.status_code == status, (
        f"{label}: expected {status}, got {response.status_code}: {response.text[:300]}"
    )
    return response


def seed() -> dict:
    users, credentials = UserRepository(), UserCredentialRepository()
    password_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()
    ids = {}
    for username, role in (("leader.queue", "leader"), ("tech.queue", "tech")):
        user_id = users.create(username, password_hash, username, role, "EU")
        credentials.create({
            "user_id": user_id,
            "password_hash": password_hash,
            "password_scheme": "legacy_sha256",
            "must_change_password": False,
        })
        ids[username] = user_id
    leader, tech = ids["leader.queue"], ids["tech.queue"]

    customers, leads, after = CustomerRepository(), LeadRepository(), AfterSalesTaskRepository()
    lead_ids = []
    for index in range(LEAD_COUNT):
        customer_id = customers.create({
            "display_name": f"Queue customer {index}",
            "normalized_name": f"queue customer {index}",
            "country": "Germany",
        }, leader)
        lead_ids.append(leads.create({
            "customer_id": customer_id,
            "owner_id": leader,
            "title": f"Queue lead {index}",
            "sales_stage": "Following",
        }, leader))
    # The oldest tasks belong to four customers and the newest to one, because
    # the list comes back newest first: this is how a hundred-and-five tasks
    # across five customers arrive as one customer on the first page.
    def add(lead_id: str, label: str) -> None:
        after.create(lead_id, {
            "assignee_id": tech,
            "status": "Open",
            "issue_type": "Technical",
            "issue_description": label,
        }, leader)

    for index in range(1, LEAD_COUNT):
        add(lead_ids[index], f"older issue on customer {index}")
    for index in range(TASK_COUNT - (LEAD_COUNT - 1)):
        add(lead_ids[0], f"newer issue {index}")

    # Won deals in three currencies, one with no currency and one with no
    # amount, so every case a reader can create is represented.
    money = []
    for amount, currency in (
        (10000, "EUR"), (10000, "EUR"), (10000, "EUR"), (10000, "EUR"),
        (1200, "USD"), (7000, "CNY"), (500, None), (None, "EUR"),
    ):
        customer_id = customers.create({
            "display_name": f"Money customer {len(money)}",
            "normalized_name": f"money customer {len(money)}",
            "country": "France",
        }, leader)
        money.append(leads.create({
            "customer_id": customer_id,
            "owner_id": leader,
            "title": f"Money lead {len(money)}",
            "sales_stage": "Won",
            "deal_amount": amount,
            "currency": currency,
            "inquiry_date": "2026-01-05",
            "po_date": "2026-02-14",
        }, leader))
    return {"ids": ids, "leads": lead_ids, "money": money}


def login(client: TestClient, username: str) -> dict:
    token = expect(client.post("/api/auth/login", json={
        "username": username, "password": PASSWORD,
    }), 200, f"login {username}").json()["token"]
    return {"Authorization": f"Bearer {token}"}


def check_every_task_can_be_reached(client: TestClient, headers: dict) -> None:
    """Reading page by page reaches all of them, and all of their customers."""
    first = expect(client.get("/api/after-sales-tasks", headers=headers),
                   200, "first page").json()
    assert len(first) < TASK_COUNT, (
        "this database no longer needs more than one page, so the test is not "
        f"exercising what it claims: {len(first)} tasks"
    )
    assert len({task["lead_id"] for task in first}) < LEAD_COUNT, (
        "the first page already covers every customer, so a truncated read "
        "would look complete"
    )

    collected = []
    limit = 500
    for offset in range(0, 10 * limit, limit):
        page = expect(client.get(
            "/api/after-sales-tasks",
            headers=headers,
            params={"limit": limit, "offset": offset},
        ), 200, f"page at {offset}").json()
        collected.extend(page)
        if len(page) < limit:
            break
    assert len(collected) == TASK_COUNT, (
        f"paging read {len(collected)} of {TASK_COUNT} tasks"
    )
    assert len({task["lead_id"] for task in collected}) == LEAD_COUNT, (
        "paging lost a customer: "
        f"{len({task['lead_id'] for task in collected})} of {LEAD_COUNT}"
    )
    assert len({task["id"] for task in collected}) == TASK_COUNT, (
        "paging returned the same task twice"
    )


def check_paging_is_stable_when_timestamps_collide(client: TestClient,
                                                   headers: dict) -> None:
    """Two rows sharing a timestamp still have one definite order.

    Without a tiebreak after the date, a page boundary can hand back one of
    them twice and lose the other - and a bulk import writes many rows in the
    same instant.
    """
    from backend.repositories.base import get_db

    conn = get_db()
    conn.execute("UPDATE after_sales_tasks SET created_at = '2026-09-08T00:00:00'")
    conn.commit()
    try:
        collected = []
        for offset in range(0, 400, 25):
            page = expect(client.get("/api/after-sales-tasks", headers=headers,
                                     params={"limit": 25, "offset": offset}),
                          200, f"page at {offset}").json()
            collected.extend(task["id"] for task in page)
            if len(page) < 25:
                break
        assert len(collected) == TASK_COUNT, (
            f"paging identical timestamps read {len(collected)} of {TASK_COUNT}"
        )
        assert len(set(collected)) == TASK_COUNT, (
            "a page boundary returned the same task twice and lost another"
        )
    finally:
        # Put the spread of timestamps back for the checks that follow.
        for index, task_id in enumerate(sorted(set(collected))):
            conn.execute("UPDATE after_sales_tasks SET created_at = ? WHERE id = ?",
                         (f"2026-09-08T00:00:{index % 60:02d}.{index:06d}", task_id))
        conn.commit()

    # Reading it back is not proof on its own: this SQLite returns rows in a
    # consistent order even with no tiebreak, so removing one would not fail
    # the check above. The order must not depend on that, so the query is read
    # for a column that is unique after the date.
    source = (ROOT / "backend" / "repositories" / "task_repository.py").read_text(
        encoding="utf-8"
    )
    paged = [line for line in source.splitlines()
             if "ORDER BY" in line and "LIMIT ? OFFSET ?" in line]
    assert len(paged) == 2, f"expected two paged task queries, found {len(paged)}"
    for line in paged:
        order = line.split("ORDER BY", 1)[1].split("LIMIT", 1)[0]
        assert ".id" in order, (
            f"a paged task query has no unique tiebreak, so two rows sharing a "
            f"timestamp have no defined order: {order.strip()}"
        )


def check_the_navigation_count_and_the_queue_agree(client: TestClient) -> None:
    """The number beside the module is the number of customers in the list."""
    tech_headers = login(client, "tech.queue")
    summary = expect(client.get("/api/tasks/workload-summary", headers=tech_headers),
                     200, "workload summary").json()
    counted = summary["after_sales_active_lead_count"]
    assert counted == LEAD_COUNT, f"the navigation count says {counted}"

    collected = []
    for offset in range(0, 5000, 500):
        page = expect(client.get("/api/after-sales-tasks", headers=tech_headers,
                                 params={"limit": 500, "offset": offset}),
                      200, "tech page").json()
        collected.extend(page)
        if len(page) < 500:
            break
    reachable = len({task["lead_id"] for task in collected})
    assert reachable == counted, (
        f"the navigation says {counted} customers and the queue can reach {reachable}"
    )


def check_amounts_are_kept_in_their_own_currency(client: TestClient, headers: dict) -> None:
    """Every place that shows a value total gets it per currency."""
    dashboard = expect(client.get("/api/review/dashboard", headers=headers),
                       200, "dashboard").json()
    by_currency = dashboard["won_value_by_currency"]
    assert by_currency.get("EUR") == 40000, by_currency
    assert by_currency.get("USD") == 1200, by_currency
    assert by_currency.get("CNY") == 7000, by_currency
    assert by_currency.get(UNSPECIFIED) == 500, (
        f"an amount with no currency was folded into one that has one: {by_currency}"
    )
    assert dashboard["amounts_missing"]["won"] == 1, (
        "the Won deal with no amount at all was not counted as missing: "
        f"{dashboard['amounts_missing']}"
    )
    # 40,000 EUR is not 48,700 of anything, and nothing may print it as one
    # currency. The scalar stays only for ordering, so it must never be the
    # only thing the answer carries.
    assert set(by_currency) >= {"EUR", "USD", "CNY", UNSPECIFIED}

    analysis = expect(client.get("/api/review/analysis", headers=headers),
                      200, "analysis").json()
    summary = analysis["summary"]
    assert summary["won_value_by_currency"].get("EUR") == 40000, summary
    assert summary["won_value_by_currency"].get("USD") == 1200, summary
    assert "40,000 EUR" in analysis["brief"], (
        f"the written brief still states a currency-free number: {analysis['brief']}"
    )
    for row in analysis.get("stage_breakdown") or []:
        assert "value_by_currency" in row, f"stage row has no subtotals: {row}"
    for key in ("owner_breakdown", "region_breakdown"):
        for row in analysis.get(key) or []:
            assert "won_value_by_currency" in row, f"{key} row has no subtotals: {row}"


def check_the_helper_refuses_to_invent_a_rate() -> None:
    """Nothing converts, and what cannot be summed is counted, not dropped."""
    rows = [
        {"amount": 10, "currency": "eur"},
        {"amount": 5, "currency": "EUR"},
        {"amount": 3, "currency": "USD"},
        {"amount": 7, "currency": None},
        {"amount": None, "currency": "USD"},
        {"amount": "not a number", "currency": "USD"},
    ]
    totals = totals_by_currency(rows, "amount")
    assert totals["by_currency"] == {"EUR": 15.0, "USD": 3.0, UNSPECIFIED: 7.0}, totals
    assert totals["missing_amount"] == 2, totals
    assert totals["missing_currency"] == 1, totals
    assert "CNY" not in totals["by_currency"], "a currency nobody used appeared"

    # An amount recorded as zero is a fact somebody entered. Dropped, it reads
    # as no record at all, and the two mean different things to a reader.
    # Amounts with decimals keep the precision the detail views need; the
    # rounding a compact KPI does is display only and never written back.
    decimals = totals_by_currency(
        [{"amount": 100.25, "currency": "EUR"}, {"amount": 0.5, "currency": "EUR"}],
        "amount",
    )
    assert decimals["by_currency"] == {"EUR": 100.75}, decimals

    zeros = totals_by_currency([{"amount": 0, "currency": "EUR"}], "amount")
    assert zeros["by_currency"] == {"EUR": 0.0}, zeros
    assert zeros["missing_amount"] == 0, (
        f"a zero amount was counted as missing: {zeros}"
    )
    assert phrase({"EUR": 0}) != phrase({}), (
        "a zero total reads exactly like no total at all"
    )
    assert "0" in phrase({"EUR": 0}) and "EUR" in phrase({"EUR": 0}), phrase({"EUR": 0})
    assert "EUR" in phrase({"EUR": 0, "USD": 5}), (
        f"a zero subtotal vanished beside a non-zero one: {phrase({'EUR': 0, 'USD': 5})}"
    )


def main() -> None:
    try:
        with TestClient(create_app()) as client:
            seed()
            headers = login(client, "leader.queue")
            check_every_task_can_be_reached(client, headers)
            check_paging_is_stable_when_timestamps_collide(client, headers)
            check_the_navigation_count_and_the_queue_agree(client)
            check_amounts_are_kept_in_their_own_currency(client, headers)
            check_the_helper_refuses_to_invent_a_rate()
    finally:
        close_db()
    print("PASS: queues can be read whole and totals stay in their own currency")


if __name__ == "__main__":
    main()
