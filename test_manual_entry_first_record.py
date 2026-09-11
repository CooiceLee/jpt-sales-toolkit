"""Somebody with nothing to import can still record their first enquiry.

The company starts with an empty database, or a salesperson gets a phone call
from a company nobody has entered yet. Until now the only way in was the email
parser, which asks for a document the caller does not have, and the "New
Inquiry" button opened exactly that. This covers the path that has to work
from nothing: find or create the customer, record the enquiry, see it in the
list, open it, change it, archive it.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_manual_entry_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import create_app  # noqa: E402
from backend.repositories import (  # noqa: E402
    UserCredentialRepository,
    UserRepository,
    close_db,
)

PASSWORD = "ManualEntry2026!"


def expect(response, status: int, label: str):
    assert response.status_code == status, (
        f"{label}: expected {status}, got {response.status_code}: {response.text[:300]}"
    )
    return response


def seed_accounts() -> dict:
    users, credentials = UserRepository(), UserCredentialRepository()
    password_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()
    ids = {}
    for username, role in (
        ("leader.entry", "leader"), ("sales.entry", "sales"), ("tech.entry", "tech"),
    ):
        user_id = users.create(username, password_hash, username, role, "EU")
        credentials.create({
            "user_id": user_id,
            "password_hash": password_hash,
            "password_scheme": "legacy_sha256",
            "must_change_password": False,
        })
        ids[username] = user_id
    return ids


def login(client: TestClient, username: str) -> dict:
    token = expect(client.post("/api/auth/login", json={
        "username": username, "password": PASSWORD,
    }), 200, f"login {username}").json()["token"]
    return {"Authorization": f"Bearer {token}"}


def check_the_database_starts_empty(client: TestClient, headers: dict) -> None:
    """Otherwise this is not the first record and the test proves nothing."""
    leads = expect(client.get("/api/leads", headers=headers), 200, "leads").json()
    assert leads == [], f"the database already holds {len(leads)} leads"


def create_by_hand(client: TestClient, headers: dict, actor_id: str,
                   company: str, title: str, email: str | None = None) -> dict:
    """The calls the form makes, in the order it makes them."""
    matches = expect(client.post("/api/customers/match", headers=headers,
                                 json={"company_name": company, "email": email}),
                     200, "match").json()
    if matches:
        customer = matches[0]
    else:
        customer = expect(client.post("/api/customers", headers=headers, json={
            "display_name": company, "country": "Germany", "city": "Berlin",
        }), 200, "create customer").json()
    customer_id = customer["id"]
    # Whoever wrote in is recorded before the enquiry that quotes them, so the
    # enquiry can point at them.
    contact = None
    if email:
        contacts = customer.get("contacts") or []
        contact = next((item for item in contacts
                        if (item.get("email") or "").lower() == email.lower()), None)
        if not contact:
            contact = expect(client.post(
                f"/api/customers/{customer_id}/contacts", headers=headers,
                json={"email": email, "is_primary": not contacts},
            ), 200, "create contact").json()
    lead = expect(client.post("/api/leads", headers=headers, json={
        "customer_id": customer_id,
        "owner_id": actor_id,
        "title": title,
        "source_channel": "manual",
        **({"primary_contact_id": contact["id"]} if contact else {}),
    }), 200, "create lead").json()
    return {"customer_id": customer_id, "lead": lead, "matched": bool(matches),
            "contact": contact}


def check_the_contact_email_is_kept(client: TestClient, ids: dict) -> None:
    """The address that was typed into the form comes back when it is reopened.

    It was used to look the company up and then thrown away: the enquiry saved
    with a company and no way to reach it, and the only copy of the address was
    in the head of whoever typed it.
    """
    headers = login(client, "leader.entry")
    made = create_by_hand(client, headers, ids["leader.entry"],
                          "Dritte Photonik AG", "Scanner enquiry",
                          email="Anna.Weber@dritte-photonik.de")
    opened = expect(client.get(f"/api/leads/{made['lead']['id']}", headers=headers),
                    200, "reopen").json()
    contacts = opened["customer"]["contacts"]
    assert [item["email"] for item in contacts] == ["anna.weber@dritte-photonik.de"], (
        f"the address typed into the form was not kept: {contacts}"
    )
    assert contacts[0]["is_primary"], "a company's first contact is not its main one"
    # An address with no name is filed under the address, not under a blank.
    assert contacts[0]["name"] == "anna.weber@dritte-photonik.de", contacts[0]["name"]
    assert opened["primary_contact_id"] == contacts[0]["id"], (
        "the enquiry does not point at the person who wrote in"
    )

    # A second enquiry from the same company, written by somebody else there.
    second = create_by_hand(client, headers, ids["leader.entry"],
                            "Dritte Photonik AG", "Second scanner enquiry",
                            email="bernd.klein@dritte-photonik.de")
    assert second["customer_id"] == made["customer_id"], (
        "recording a second contact created a second copy of the company"
    )
    reopened = expect(client.get(f"/api/leads/{second['lead']['id']}", headers=headers),
                      200, "reopen second").json()
    contacts = reopened["customer"]["contacts"]
    assert {item["email"] for item in contacts} == {
        "anna.weber@dritte-photonik.de", "bernd.klein@dritte-photonik.de",
    }, f"both people are not on file: {contacts}"
    bernd = next(item for item in contacts
                 if item["email"] == "bernd.klein@dritte-photonik.de")
    assert reopened["primary_contact_id"] == bernd["id"], (
        "the second enquiry does not point at the person who sent it"
    )
    assert not bernd["is_primary"], (
        "the second enquiry took over who the company's main contact is"
    )

    # Recording the same person again attaches to them instead of failing or
    # filing a duplicate.
    again = create_by_hand(client, headers, ids["leader.entry"],
                           "Dritte Photonik AG", "Third scanner enquiry",
                           email="anna.weber@dritte-photonik.de")
    assert again["contact"]["id"] == made["contact"]["id"], (
        "the same address was filed a second time"
    )


def check_leader_records_the_first_enquiry(client: TestClient, ids: dict) -> dict:
    headers = login(client, "leader.entry")
    check_the_database_starts_empty(client, headers)
    made = create_by_hand(client, headers, ids["leader.entry"],
                          "Erste Laser GmbH", "Cutting head enquiry")
    lead = made["lead"]
    assert not made["matched"], "an empty database matched an existing customer"
    assert lead["display_id"], "the new enquiry has no readable number"
    # The stage is the endpoint's own default, not one the form invented.
    assert lead["sales_stage"] == "New", lead["sales_stage"]

    listed = expect(client.get("/api/leads", headers=headers), 200, "list").json()
    assert [item["id"] for item in listed] == [lead["id"]], (
        "the enquiry that was just created is not in the list"
    )
    opened = expect(client.get(f"/api/leads/{lead['id']}", headers=headers),
                    200, "detail").json()
    assert opened["customer"]["display_name"] == "Erste Laser GmbH"
    assert opened["title"] == "Cutting head enquiry"
    return {"headers": headers, "lead": lead, "customer_id": made["customer_id"]}


def check_a_second_enquiry_reuses_the_customer(client: TestClient, ids: dict,
                                               first: dict) -> None:
    """A company already on file does not get a second copy of itself."""
    headers = first["headers"]
    made = create_by_hand(client, headers, ids["leader.entry"],
                          "Erste Laser GmbH", "Second project")
    assert made["matched"], "the existing customer was not offered as a match"
    assert made["customer_id"] == first["customer_id"], (
        "a second enquiry created a duplicate of a customer already on file"
    )
    customers = expect(client.get("/api/customers", headers=headers,
                                  params={"search": "Erste"}),
                       200, "customers").json()
    named = [item for item in customers if item["display_name"] == "Erste Laser GmbH"]
    assert len(named) == 1, f"{len(named)} copies of the same company exist"


def check_both_companies_of_one_name_are_offered(client: TestClient,
                                                 ids: dict) -> None:
    """Two real companies share a name. The reader must be able to pick either.

    The form offers what the match call returns. While that returned the first
    company of a name and stopped, the second one could not be chosen at all:
    an enquiry from it was either filed under the wrong company or created yet
    another copy - and the copy is what the next reader would then be offered.
    """
    headers = login(client, "leader.entry")
    cities = {}
    for city in ("Jena", "Ulm"):
        customer = expect(client.post("/api/customers", headers=headers, json={
            "display_name": "Doppel Photonics GmbH", "country": "Germany",
            "city": city,
        }), 200, f"create {city}").json()
        cities[city] = customer["id"]

    matches = expect(client.post("/api/customers/match", headers=headers, json={
        "company_name": "Doppel Photonics GmbH", "email": None,
    }), 200, "match").json()
    offered = {item["id"]: item.get("city") for item in matches}
    assert set(offered) == set(cities.values()), (
        "the namesake in "
        f"{sorted(set(cities) - {offered.get(i) for i in offered})} was not offered: "
        f"{[item.get('city') for item in matches]}"
    )
    # Told apart on the page by more than the name they share.
    assert sorted(filter(None, offered.values())) == ["Jena", "Ulm"], offered

    # And filing an enquiry against the chosen one keeps it there.
    lead = expect(client.post("/api/leads", headers=headers, json={
        "customer_id": cities["Ulm"], "owner_id": ids["leader.entry"],
        "title": "Enquiry from the Ulm plant", "source_channel": "manual",
    }), 200, "create lead").json()
    reopened = expect(client.get(f"/api/leads/{lead['id']}", headers=headers),
                      200, "reopen").json()
    assert reopened["customer_id"] == cities["Ulm"], (
        "the enquiry moved to the other company of the same name"
    )
    customers = expect(client.get("/api/customers", headers=headers,
                                  params={"search": "Doppel"}), 200, "customers").json()
    named = [item for item in customers
             if item["display_name"] == "Doppel Photonics GmbH"]
    assert len(named) == 2, f"{len(named)} companies of that name exist, expected 2"


def check_sales_can_start_from_nothing(client: TestClient, ids: dict) -> None:
    """A salesperson records their own enquiry, and only their own."""
    headers = login(client, "sales.entry")
    made = create_by_hand(client, headers, ids["sales.entry"],
                          "Zweite Optik SARL", "Beam delivery enquiry")
    assert made["lead"]["owner_id"] == ids["sales.entry"]

    # And cannot file one under somebody else's name.
    refused = client.post("/api/leads", headers=headers, json={
        "customer_id": made["customer_id"],
        "owner_id": ids["leader.entry"],
        "title": "Filed under the leader",
    })
    assert refused.status_code == 403, (
        f"a salesperson created a lead owned by somebody else: {refused.status_code}"
    )


def check_the_contact_boundary_still_holds(client: TestClient, ids: dict) -> None:
    """A contact needs a name or an address - the rule did not get weaker.

    The form has only an email field, and the endpoint used to demand a name,
    so an address typed into it could not be saved at all. The name is optional
    now; what a contact still cannot be is empty, and who may create one has
    not changed.
    """
    headers = login(client, "leader.entry")
    customer_id = expect(client.post("/api/customers", headers=headers, json={
        "display_name": "Vierte Systeme GmbH",
    }), 200, "create customer").json()["id"]

    empty = client.post(f"/api/customers/{customer_id}/contacts", headers=headers,
                        json={"phone": "+49 30 123456"})
    assert empty.status_code == 400, (
        "a contact with neither a name nor an address was accepted, or was "
        f"refused as a server error: {empty.status_code} {empty.text[:200]}"
    )
    blank = client.post(f"/api/customers/{customer_id}/contacts", headers=headers,
                        json={"name": "   ", "email": ""})
    assert blank.status_code == 400, f"{blank.status_code} {blank.text[:200]}"
    bad_address = client.post(f"/api/customers/{customer_id}/contacts",
                              headers=headers, json={"email": "not-an-address"})
    assert bad_address.status_code == 400, (
        f"{bad_address.status_code} {bad_address.text[:200]}"
    )
    named = expect(client.post(f"/api/customers/{customer_id}/contacts",
                               headers=headers, json={"name": "Katrin Vogel"}),
                   200, "name only")
    assert named.json()["name"] == "Katrin Vogel"
    addressed = expect(client.post(f"/api/customers/{customer_id}/contacts",
                                   headers=headers,
                                   json={"email": "kv@vierte.de", "is_primary": False}),
                       200, "email only")
    assert addressed.json()["email"] == "kv@vierte.de"

    # And a technical account still cannot record one.
    tech = login(client, "tech.entry")
    refused = client.post(f"/api/customers/{customer_id}/contacts", headers=tech,
                          json={"email": "tech@vierte.de"})
    assert refused.status_code == 403, (
        f"a technical account created a contact: {refused.status_code}"
    )


def check_a_value_outside_the_allowed_set_is_answered(client: TestClient, ids: dict) -> None:
    """Five fields on a lead are constrained; the database is not the boundary.

    A grade of "High" - the word the interface uses for a different field -
    reached SQLite, whose CHECK constraint failed as an unhandled error. The
    caller got a 500 that named neither the field nor what it accepts, and the
    log carried a stack trace for what is an ordinary bad request.
    """
    headers = login(client, "leader.entry")
    customer_id = expect(client.post("/api/customers", headers=headers, json={
        "display_name": "Fünfte Optik GmbH",
    }), 200, "create customer").json()["id"]
    lead = expect(client.post("/api/leads", headers=headers, json={
        "customer_id": customer_id, "owner_id": ids["leader.entry"],
        "title": "Grade probe", "source_channel": "manual",
    }), 200, "create lead").json()

    for field, wrong in (
        ("quality_grade", "High"), ("sales_stage", "Negotiating"),
        ("service_status", "Pending"), ("fulfillment_status", "Shipped"),
        ("urgency", "Urgent"),
    ):
        refused = client.patch(f"/api/leads/{lead['id']}", headers=headers, json={
            field: wrong, "row_version": lead["row_version"],
        })
        assert refused.status_code == 422, (
            f"{field}={wrong!r} was answered with {refused.status_code}, not a "
            f"bad request: {refused.text[:200]}"
        )
        assert field in refused.text, (
            f"the refusal for {field} does not say which field: {refused.text[:200]}"
        )

    # And the values the schema does allow still go through.
    current = expect(client.get(f"/api/leads/{lead['id']}", headers=headers),
                     200, "read").json()
    graded = expect(client.patch(f"/api/leads/{lead['id']}", headers=headers, json={
        "quality_grade": "A", "urgency": "High",
        "row_version": current["row_version"],
    }), 200, "grade it").json()
    assert graded["quality_grade"] == "A" and graded["urgency"] == "High"


def check_a_technical_account_is_refused(client: TestClient, ids: dict) -> None:
    """The entry point is not offered to Tech, and the server refuses it too."""
    headers = login(client, "tech.entry")
    refused = client.post("/api/customers", headers=headers,
                          json={"display_name": "Tech tried this"})
    assert refused.status_code == 403, refused.status_code
    refused = client.post("/api/leads", headers=headers, json={
        "customer_id": "anything", "owner_id": ids["tech.entry"], "title": "Nope",
    })
    assert refused.status_code == 403, refused.status_code


def check_a_refused_enquiry_leaves_no_lead(client: TestClient, ids: dict) -> None:
    """A save that fails must not leave a record nobody can explain."""
    headers = login(client, "leader.entry")
    before = len(expect(client.get("/api/leads", headers=headers), 200, "before").json())
    refused = client.post("/api/leads", headers=headers, json={
        "customer_id": "no-such-customer",
        "owner_id": ids["leader.entry"],
        "title": "Points at nothing",
    })
    assert refused.status_code in (400, 404), refused.status_code
    after = len(expect(client.get("/api/leads", headers=headers), 200, "after").json())
    assert after == before, f"a refused save still created a lead: {before} -> {after}"


def check_the_first_record_can_be_corrected(client: TestClient, first: dict) -> None:
    """Recording something is only useful if it can be put right afterwards."""
    headers, lead = first["headers"], first["lead"]
    current = expect(client.get(f"/api/leads/{lead['id']}", headers=headers),
                     200, "read").json()
    updated = expect(client.patch(f"/api/leads/{lead['id']}", headers=headers, json={
        "title": "Cutting head enquiry (corrected)",
        "row_version": current["row_version"],
    }), 200, "correct").json()
    assert updated["title"] == "Cutting head enquiry (corrected)"

    expect(client.post(f"/api/leads/{lead['id']}/archive", headers=headers,
                       json={"row_version": updated["row_version"]}),
           200, "archive")
    listed = expect(client.get("/api/leads", headers=headers), 200, "after archive").json()
    assert lead["id"] not in {item["id"] for item in listed}, (
        "an archived enquiry is still in the working list"
    )


def main() -> None:
    try:
        with TestClient(create_app()) as client:
            ids = seed_accounts()
            first = check_leader_records_the_first_enquiry(client, ids)
            check_a_second_enquiry_reuses_the_customer(client, ids, first)
            check_both_companies_of_one_name_are_offered(client, ids)
            check_the_contact_email_is_kept(client, ids)
            check_the_contact_boundary_still_holds(client, ids)
            check_a_value_outside_the_allowed_set_is_answered(client, ids)
            check_sales_can_start_from_nothing(client, ids)
            check_a_technical_account_is_refused(client, ids)
            check_a_refused_enquiry_leaves_no_lead(client, ids)
            check_the_first_record_can_be_corrected(client, first)
    finally:
        close_db()
    print("PASS: a first enquiry can be recorded by hand, corrected and archived")


if __name__ == "__main__":
    main()
