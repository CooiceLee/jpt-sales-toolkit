"""Regression coverage for owner-account business-region filtering."""

from pathlib import Path

from backend.config import init_settings
from backend.repositories import (
    CustomerRepository,
    LeadRepository,
    PreSalesTaskRepository,
    UserRepository,
    init_db,
)
from backend.services.business_region_service import (
    InvalidBusinessRegionError,
    get_business_region_service,
)
from backend.services.lead_service import LeadService
from backend.services.member_authorization_validation import validate_member_profile
from backend.services.member_authorization_presenter import present_member


def build_fixture() -> dict:
    output = Path("test_output")
    output.mkdir(exist_ok=True)
    db_path = output / "test_business_regions.sqlite"
    if db_path.exists():
        db_path.unlink()
    settings = init_settings(Path.cwd())
    settings.db_path = db_path
    init_db(str(db_path))

    users = UserRepository()
    leader = users.create("leader", "dummy", "Leader", "leader", region="Global")
    global_sales = users.create("global", "dummy", "Global Sales", "sales", region="Global")
    euro_sales = users.create("euro", "dummy", "Euro Sales", "sales", region="Euro")
    cn_euro_sales = users.create("cn-euro", "dummy", "欧洲销售", "sales", region="欧洲")
    sea_sales = users.create("sea", "dummy", "SEA Sales", "sales", region="SEA")
    tech = users.create("tech", "dummy", "Tech", "tech", region="Euro")

    customers = CustomerRepository()
    leads = LeadRepository()
    lead_ids = {}
    for key, owner, country in (
        ("global", global_sales, "France"),
        ("euro", euro_sales, "Germany"),
        ("cn_euro", cn_euro_sales, "France"),
        ("sea", sea_sales, "Singapore"),
    ):
        customer_id = customers.create(
            {
                "display_name": f"{key} customer",
                "normalized_name": f"{key} customer",
                "country": country,
            },
            leader,
        )
        lead_ids[key] = leads.create(
            {
                "customer_id": customer_id,
                "owner_id": owner,
                "title": f"{key} opportunity",
                "sales_stage": "Following",
            },
            owner,
        )

    PreSalesTaskRepository().create(
        lead_ids["euro"], {"assignee_id": tech, "status": "Open"}, leader
    )
    return {
        "leader": leader,
        "global_sales": global_sales,
        "euro_sales": euro_sales,
        "tech": tech,
        "leads": lead_ids,
    }


def test_region_definitions_and_aliases() -> None:
    service = get_business_region_service()
    assert [item["code"] for item in service.definitions] == [
        "GLOBAL", "EU", "NA_CA_AU", "RU_TR_ME", "SEA"
    ]
    assert service.normalize("Global") == "GLOBAL"
    assert service.normalize("Euro") == "EU"
    assert service.normalize("欧洲") == "EU"
    assert service.normalize("Southeast Asia") == "SEA"
    try:
        service.normalize("Americas", allow_none=False)
    except InvalidBusinessRegionError:
        pass
    else:
        raise AssertionError("unknown regions must be rejected")


def test_region_intersects_permissions_and_other_filters(ids: dict) -> None:
    service = LeadService()
    all_rows = service.list(ids["leader"], "leader")
    global_rows = service.list(ids["leader"], "leader", business_region="GLOBAL")
    europe_rows = service.list(ids["leader"], "leader", business_region="EU")
    assert len(all_rows) == 4
    assert [item["id"] for item in global_rows] == [ids["leads"]["global"]]
    assert {item["id"] for item in europe_rows} == {
        ids["leads"]["euro"], ids["leads"]["cn_euro"]
    }

    combined = service.list(
        ids["leader"],
        "leader",
        owner_id=ids["euro_sales"],
        business_region="EU",
        search="euro customer",
    )
    assert [item["id"] for item in combined] == [ids["leads"]["euro"]]
    assert service.list(
        ids["leader"],
        "leader",
        owner_id=ids["euro_sales"],
        business_region="GLOBAL",
    ) == []

    sales_rows = service.list(
        ids["global_sales"], "sales", business_region="EU"
    )
    assert sales_rows == []
    tech_rows = service.list(ids["tech"], "tech", business_region="EU")
    assert [item["id"] for item in tech_rows] == [ids["leads"]["euro"]]
    assert service.list(ids["tech"], "tech", business_region="GLOBAL") == []


def test_member_region_validation() -> None:
    validate_member_profile(
        {
            "username": "member",
            "display_name": "Member",
            "role": "sales",
            "region": "North America / Canada / Australia",
        },
        require_all=True,
    )
    for missing in (None, "", "   "):
        try:
            validate_member_profile(
                {
                    "username": "member",
                    "display_name": "Member",
                    "role": "sales",
                    "region": missing,
                },
                require_all=True,
            )
        except ValueError as exc:
            assert str(exc) == "Business region is required"
        else:
            raise AssertionError("new members must select a business region")
    try:
        validate_member_profile({"region": "Americas"})
    except InvalidBusinessRegionError:
        pass
    else:
        raise AssertionError("member region must use the five business regions")
    legacy = present_member(
        {
            "id": "legacy", "username": "legacy", "display_name": "Legacy",
            "role": "sales", "region": None, "is_active": True,
        },
        type("Authorizations", (), {"list_for_user": lambda self, _user_id: []})(),
    )
    assert legacy["region"] is None


def test_frontend_uses_shared_business_region_filter() -> None:
    root = Path(__file__).parent
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (root / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    view = (root / "frontend" / "js" / "modules" / "stage-filter-view.js").read_text(
        encoding="utf-8"
    )
    data = (root / "frontend" / "js" / "modules" / "stage-filter-data.js").read_text(
        encoding="utf-8"
    )
    navigation = (
        root / "frontend" / "js" / "modules" / "lead-navigation.js"
    ).read_text(encoding="utf-8")
    assert "businessRegion: ''" in app
    assert "business_regions" in view and "stage-region-" in view
    assert "filters.business_region = State.stageFilters.businessRegion" in data
    assert "State.stageFilters.businessRegion = '';" in navigation
    assert 'id="filter-region"' not in index
    assert 'id="followup-region"' not in index
    for code in ("GLOBAL", "EU", "NA_CA_AU", "RU_TR_ME", "SEA"):
        assert f'value="{code}"' in index
    assert 'id="bootstrap-region" title="Business region" required' in index
    assert 'id="authorization-member-region" title="Business region" required' in index
    bootstrap = (
        root / "frontend" / "js" / "modules" / "authorization-bootstrap.js"
    ).read_text(encoding="utf-8")
    members = (
        root / "frontend" / "js" / "modules" / "authorization-member-actions.js"
    ).read_text(encoding="utf-8")
    assert "Business region is required." in bootstrap
    assert "Business region is required." in members


def main() -> None:
    test_region_definitions_and_aliases()
    ids = build_fixture()
    test_region_intersects_permissions_and_other_filters(ids)
    test_member_region_validation()
    test_frontend_uses_shared_business_region_filter()
    print("PASS: canonical business-region filters and permission intersections")


if __name__ == "__main__":
    main()
