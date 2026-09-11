"""Who gets visited first may not depend on which currency they quote in.

Amounts in this database are in whatever currency the enquiry arrived in, and
there is no conversion anybody has agreed to. The trip candidate score added
them up anyway and divided by ten thousand, so 5,000,000 JPY pushed a customer
to the top of the list over an identical customer holding 5,000 EUR - and the
ordering behind "who should I see on this trip" is not a display detail.

The score now orders by what can be compared - how many open leads, how many
quoted, how recently anything happened - and says nothing about the amount at
all. The amounts are reported per currency, which is the only form in which
they are true, and the order of a trip's stops stays the reader's to adjust.

Whether order size should weigh was the owner's decision and it is settled
(2026-09-09): order size does not enter the automatic score at all. A fixed
"has an amount" bonus was proposed and refused. So this file pins the whole
rule, not half of it: no amount is scored, no amount breaks a tie between
equal scores, a missing amount costs nothing, and a missing amount, a zero and
an unknown currency stay three different things.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_currency_priority_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import create_app  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402

LEADER = ("priority.leader", "PriorityLeader2026")
SALES = [("priority.sales1", "PrioritySales2026A"), ("priority.sales2", "PrioritySales2026B")]


def expect(response, status: int, label: str):
    assert response.status_code == status, (
        f"{label}: expected {status}, got {response.status_code}: {response.text[:300]}"
    )
    return response


def login(client: TestClient, username: str, password: str) -> dict:
    token = expect(client.post("/api/auth/login", json={
        "username": username, "password": password,
    }), 200, f"login {username}").json()["token"]
    return {"Authorization": f"Bearer {token}"}


def make_customer(client: TestClient, headers: dict, name: str, index: int) -> str:
    created = expect(client.post("/api/customers", headers=headers, json={
        "display_name": name, "country": "Germany", "city": f"City {index}",
        "region": "EU", "lat": 52.0 + index, "lng": 13.0 + index,
        "geocode_source": "manual", "geocode_confidence": "high",
        "geocode_locked": True,
    }), 200, f"create customer {name}").json()
    return created["id"]


def quote(client: TestClient, headers: dict, customer_id: str, owner_id: str,
          title: str, amount=None, currency=None, stage: str = "Quoted",
          product: str | None = None) -> dict:
    lead = expect(client.post("/api/leads", headers=headers, json={
        "customer_id": customer_id, "owner_id": owner_id, "title": title,
        "source_channel": "manual",
        **({"product_category": product} if product else {}),
    }), 200, "create lead").json()
    patch = {"sales_stage": stage, "row_version": lead["row_version"]}
    if amount is not None:
        patch["estimated_value" if stage != "Won" else "deal_amount"] = amount
    if currency is not None:
        patch["currency"] = currency
    return expect(client.patch(f"/api/leads/{lead['id']}", headers=headers, json=patch),
                  200, "quote lead").json()


def check_the_same_situation_scores_the_same_in_any_currency(client, headers, owner_id):
    """Four customers, one open quoted lead each. Only the money differs."""
    cases = [
        ("Small in euros", 5_000, "EUR"),
        ("Large in yen", 5_000_000, "JPY"),
        ("Amount, currency never recorded", 5_000, None),
        ("No amount at all", None, None),
        # Priced at zero: still worth showing as zero, still not money on the
        # table for the purpose of deciding whose door to knock on.
        ("Priced at zero", 0, "EUR"),
    ]
    for index, (name, amount, currency) in enumerate(cases, start=1):
        customer_id = make_customer(client, headers, name, index)
        quote(client, headers, customer_id, owner_id, f"{name} enquiry",
              amount=amount, currency=currency)

    data = expect(client.get("/api/review/trip-candidates?region=EU&limit=50",
                             headers=headers), 200, "candidates").json()
    scores = {item["customer_name"]: item["score"] for item in data["candidates"]}
    assert len(scores) == 5, scores

    # Five customers in the same business situation - one open quoted lead
    # each - and the money on them differs in every way it can: currency,
    # magnitude, unknown currency, an explicit zero, nothing at all. The
    # priority is the same for all five, because the amount is not in it.
    #
    # Order size does not enter the score - the owner settled that on
    # 2026-09-09 - so nothing about the amount is scored.
    assert len(set(scores.values())) == 1, (
        f"the amount is deciding priority again: {scores}"
    )

    # And it does not decide the tie either. Five equal scores come back in
    # name order, which a reader can predict; ordering them by "who has the
    # biggest number on them" would put the 5,000,000 first and read as a
    # value ranking through the back door.
    order = [item["customer_name"] for item in data["candidates"]]
    assert order == sorted(order), (
        f"equal priorities are ordered by something other than the name: {order}"
    )
    assert order[0] != "Large in yen", (
        "the largest amount is breaking the tie, so the amount is ranking "
        f"customers again: {order}"
    )
    # A customer with no amount recorded is not pushed to the back for it.
    assert order.index("No amount at all") < order.index("Small in euros"), (
        f"a missing amount is being treated as no value: {order}"
    )

    by_name = {item["customer_name"]: item for item in data["candidates"]}
    assert by_name["Large in yen"]["pipeline_value_by_currency"] == {"JPY": 5_000_000.0}
    assert by_name["Small in euros"]["pipeline_value_by_currency"] == {"EUR": 5_000.0}
    assert by_name["Amount, currency never recorded"]["pipeline_value_by_currency"] == {
        "UNSPECIFIED": 5_000.0
    }, "an amount with no currency was dropped instead of being shown as unknown"
    assert by_name["No amount at all"]["pipeline_value_by_currency"] == {}
    assert by_name["Priced at zero"]["pipeline_value_by_currency"] == {"EUR": 0.0}, (
        "a price of zero stopped being shown, so it reads as never priced"
    )

    # And no total across them anywhere: not on a candidate, not in the summary.
    for item in data["candidates"]:
        assert "pipeline_value" not in item, (
            f"a cross-currency total is back on a candidate: {item['customer_name']}"
        )
        assert "won_value" not in item
    assert "pipeline_value" not in data["summary"], data["summary"]
    assert data["summary"]["pipeline_value_by_currency"] == {
        "EUR": 5_000.0, "JPY": 5_000_000.0, "UNSPECIFIED": 5_000.0,
    }, data["summary"]["pipeline_value_by_currency"]

    # The reader is still told who has money on the table - as a fact beside
    # the customer, not as a number folded into the priority.
    assert "Pipeline value" in by_name["Large in yen"]["reasons"]
    assert "Pipeline value" in by_name["Amount, currency never recorded"]["reasons"]
    assert "Pipeline value" not in by_name["No amount at all"]["reasons"]
    assert "Pipeline value" not in by_name["Priced at zero"]["reasons"]
    assert by_name["Priced at zero"]["has_pipeline"] is False
    assert by_name["Amount, currency never recorded"]["has_pipeline"] is True


def check_more_deals_outrank_a_bigger_denomination(client, headers, owner_ids):
    """Owner performance is ordered by what can be compared: the deals won."""
    one_big = make_customer(client, headers, "One large yen deal", 11)
    quote(client, headers, one_big, owner_ids[0], "Single big win",
          amount=900_000_000, currency="JPY", stage="Won")
    for index in (12, 13):
        customer_id = make_customer(client, headers, f"Euro deal {index}", index)
        quote(client, headers, customer_id, owner_ids[1], f"Win {index}",
              amount=1_000, currency="EUR", stage="Won")

    analysis = expect(client.get("/api/review/analysis", headers=headers),
                      200, "analysis").json()
    owners = analysis["owner_breakdown"]
    ranked = [row["label"] for row in owners]
    two_wins = next(row for row in owners if row["won"] == 2)
    one_win = next(row for row in owners if row["won"] == 1
                   and row["won_value_by_currency"].get("JPY"))
    assert ranked.index(two_wins["label"]) < ranked.index(one_win["label"]), (
        "one deal in a large-denomination currency outranked two won deals: "
        f"{[(row['label'], row['won'], row['won_value_by_currency']) for row in owners]}"
    )
    for row in owners:
        assert "won_value" not in row and "pipeline_value" not in row, (
            f"a cross-currency total is back in the owner breakdown: {row}"
        )
    for row in analysis["stage_breakdown"]:
        assert "value" not in row, f"a cross-currency stage total is back: {row}"
    assert "won_value" not in analysis["summary"], analysis["summary"]
    assert "average_won_value" not in analysis["summary"], (
        "an average across currencies is back in the summary"
    )
    assert analysis["summary"]["won_value_by_currency"] == {
        "JPY": 900_000_000.0, "EUR": 2_000.0,
    }, analysis["summary"]["won_value_by_currency"]


def check_the_lead_lists_do_not_rank_across_currencies(client, headers, owner_id):
    """Risk and "high value" are lists somebody works down from the top."""
    product = "CurrencyProbe"
    amounts = [("JPY", 5_000_000), ("JPY", 4_000_000), ("JPY", 3_000_000),
               ("EUR", 60_000)]
    for index, (currency, amount) in enumerate(amounts, start=20):
        customer_id = make_customer(client, headers, f"{currency} {amount}", index)
        quote(client, headers, customer_id, owner_id, f"{currency} {amount} enquiry",
              amount=amount, currency=currency, product=product)

    analysis = expect(client.get(
        f"/api/review/analysis?product_category={product}", headers=headers),
        200, "analysis").json()

    # A threshold in one currency applied to amounts in another said a deal
    # was large because of the denomination it was quoted in.
    for row in analysis["risk_leads"]:
        assert "High value" not in row["risk_reasons"], (
            f"an amount threshold is being applied across currencies: {row}"
        )

    # The biggest in each currency comes first - the currencies themselves in
    # name order, which claims nothing - and only then the second biggest.
    # Three yen deals can no longer fill the table and call themselves the top
    # of the pipeline.
    ranked = [(row["currency"], row["value"])
              for row in analysis["high_value_open_leads"]]
    assert ranked == [("EUR", 60_000.0), ("JPY", 5_000_000.0),
                      ("JPY", 4_000_000.0), ("JPY", 3_000_000.0)], (
        "the largest open leads are ranked by nominal amount across "
        f"currencies: {ranked}"
    )
    # And the column the table prints from is actually filled in.
    for row in analysis["high_value_open_leads"]:
        assert row["value_by_currency"] == {row["currency"]: row["value"]}, row


def check_the_shown_lead_is_the_one_being_worked_on(client, headers, owner_id):
    """One customer, two leads in the same stage: the older one has an amount
    on it, the newer one does not and was touched last. Amount-filled-in used
    to outrank the timestamp here, so the customer's row pointed at the lead
    nobody had touched for longer - a completeness artefact, because the
    amounts in this database are patchy. The stage decides, then who was
    worked on last, then a stable id."""
    customer_id = make_customer(client, headers, "Two leads, one amount", 9)
    with_amount = quote(client, headers, customer_id, owner_id,
                        "Priced enquiry", amount=90_000, currency="EUR",
                        stage="Following")
    without_amount = quote(client, headers, customer_id, owner_id,
                           "Unpriced enquiry", stage="Following")
    # Touched last, and still without an amount.
    without_amount = expect(client.patch(
        f"/api/leads/{without_amount['id']}", headers=headers,
        json={"next_followup_date": "2026-10-01",
              "row_version": without_amount["row_version"]},
    ), 200, "touch the unpriced lead").json()
    assert (without_amount["updated_at"] or "") > (with_amount["updated_at"] or ""), (
        "the unpriced lead is not the more recently touched one, so this case "
        "cannot tell the two rules apart"
    )

    data = expect(client.get("/api/review/trip-candidates?region=EU&limit=50",
                             headers=headers), 200, "candidates").json()
    row = next(item for item in data["candidates"]
               if item["customer_name"] == "Two leads, one amount")
    assert row["primary_lead_id"] == without_amount["id"], (
        "the lead shown for this customer is the one with an amount on it "
        "rather than the one being worked on: "
        f"{row['primary_lead_display_id']} vs {without_amount['display_id']}"
    )
    # The amounts are still reported, per currency - they are just not
    # deciding which lead stands for the customer.
    assert row["pipeline_value_by_currency"] == {"EUR": 90_000.0}, row

    # A stage still outranks the timestamp: quoting the priced lead makes it
    # the one to show, even though the other was touched more recently.
    expect(client.patch(f"/api/leads/{with_amount['id']}", headers=headers,
                        json={"sales_stage": "Quoted",
                              "row_version": with_amount["row_version"]}),
           200, "quote the priced lead")
    expect(client.patch(f"/api/leads/{without_amount['id']}", headers=headers,
                        json={"next_followup_date": "2026-10-02",
                              "row_version": without_amount["row_version"]}),
           200, "touch the unpriced lead again")
    data = expect(client.get("/api/review/trip-candidates?region=EU&limit=50",
                             headers=headers), 200, "candidates").json()
    row = next(item for item in data["candidates"]
               if item["customer_name"] == "Two leads, one amount")
    assert row["primary_stage"] == "Quoted", (
        f"the business stage stopped deciding: {row['primary_stage']}"
    )
    assert row["primary_lead_id"] == with_amount["id"], row["primary_lead_display_id"]

    # Two leads saved in the same instant is what the stable id is for. The API
    # will not produce that tie on request, so the rule is checked where it
    # lives: the same stage, the same timestamp, and the answer must be the
    # same lead every time - not "whichever the sort happened to leave first".
    from backend.services.review_service import ReviewService

    same_instant = [
        {"id": "lead-b", "display_id": "JPT-2609-0002", "sales_stage": "Following",
         "updated_at": "2026-09-09T08:00:00+00:00", "estimated_value": None},
        {"id": "lead-a", "display_id": "JPT-2609-0001", "sales_stage": "Following",
         "updated_at": "2026-09-09T08:00:00+00:00", "estimated_value": 90_000},
    ]
    service = ReviewService()
    picked = {
        service._trip_candidate_from_point(
            {"customer_id": "c", "customer_name": "Same instant",
             "leads": order, "lead_count": 2},
            missing_location=False,
        )["primary_lead_id"]
        for order in (same_instant, list(reversed(same_instant)))
    }
    # One answer, whichever order the rows arrive in, and it is the later
    # business id - not the row that happens to carry an amount.
    assert picked == {"lead-b"}, (
        "with the stage and the timestamp equal the shown lead depends on the "
        f"order the rows arrived in, or on the amount: {picked}"
    )


def main() -> None:
    try:
        with TestClient(create_app()) as client:
            upsert_account(LEADER[0], LEADER[1], "Priority Leader", "leader", None)
            for username, password in SALES:
                upsert_account(username, password, username, "sales", None)
            headers = login(client, *LEADER)
            users = expect(client.get("/api/auth/users", headers=headers),
                           200, "users").json()
            ids = {user["username"]: user["id"] for user in users}
            owner_ids = [ids[SALES[0][0]], ids[SALES[1][0]]]

            check_the_same_situation_scores_the_same_in_any_currency(
                client, headers, owner_ids[0])
            check_more_deals_outrank_a_bigger_denomination(client, headers, owner_ids)
            check_the_lead_lists_do_not_rank_across_currencies(
                client, headers, owner_ids[0])
            check_the_shown_lead_is_the_one_being_worked_on(
                client, headers, owner_ids[0])
    finally:
        close_db()
    print("PASS: priority is decided by the business situation, not the currency")


if __name__ == "__main__":
    main()
