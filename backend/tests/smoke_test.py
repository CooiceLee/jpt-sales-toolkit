"""
Smoke tests for MVP flow.

Usage:
    1. Start server: uvicorn backend.app_v2:app --port 8000
    2. Run tests: python -m backend.tests.smoke_test <username> <password>

Tests the complete MVP flow:
    - Login
    - Create customer
    - Create lead via intake
    - Add follow-up activity
    - Create pre-sales task
    - Upload attachment
    - Get system info
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000/api"

# Disable proxy for local testing
SESSION = requests.Session()
SESSION.trust_env = False


class SmokeTest:
    """Smoke test runner."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.token = None
        self.user = None
        self.customer_id = None
        self.lead_id = None
        self.results = []

    def log(self, test_name: str, success: bool, message: str = ""):
        status = "✓" if success else "✗"
        self.results.append((test_name, success, message))
        print(f"  {status} {test_name}: {message}")

    def run_all(self):
        """Run all smoke tests."""
        print("\n=== JPT Sales Toolkit Smoke Tests ===\n")

        # Auth tests
        self.test_login()
        if not self.token:
            print("\n✗ Cannot continue without login")
            return self.summary()

        self.test_get_me()

        # Customer tests
        self.test_create_customer()

        # Lead intake tests
        self.test_intake_submit()

        # Activity tests
        if self.lead_id:
            self.test_add_follow_up()
            self.test_create_pre_sales_task()
            self.test_list_attachments()

        # Admin tests
        self.test_system_info()

        return self.summary()

    def summary(self):
        """Print test summary."""
        passed = sum(1 for _, success, _ in self.results if success)
        total = len(self.results)
        print(f"\n=== Summary: {passed}/{total} tests passed ===\n")
        return passed == total

    def headers(self):
        """Get auth headers."""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_login(self):
        """Test POST /auth/login"""
        try:
            resp = SESSION.post(
                f"{BASE_URL}/auth/login",
                json={"username": self.username, "password": self.password},
            )
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token")
                self.user = data.get("user")
                self.log("login", True, f"user_id={self.user.get('id', '?')[:8]}...")
            else:
                self.log("login", False, f"status={resp.status_code}, {resp.text[:100]}")
        except Exception as e:
            self.log("login", False, str(e))

    def test_get_me(self):
        """Test GET /auth/me"""
        try:
            resp = SESSION.get(f"{BASE_URL}/auth/me", headers=self.headers())
            if resp.status_code == 200:
                data = resp.json()
                self.log("get_me", True, f"role={data.get('role')}")
            else:
                self.log("get_me", False, f"status={resp.status_code}")
        except Exception as e:
            self.log("get_me", False, str(e))

    def test_create_customer(self):
        """Test POST /customers"""
        try:
            resp = SESSION.post(
                f"{BASE_URL}/customers",
                headers=self.headers(),
                json={
                    "display_name": "Test Company Ltd",
                    "country": "United Kingdom",
                    "city": "London",
                    "industry": "Manufacturing",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self.customer_id = data.get("id")
                self.log("create_customer", True, f"id={self.customer_id[:8]}...")
            else:
                self.log("create_customer", False, f"status={resp.status_code}, {resp.text[:100]}")
        except Exception as e:
            self.log("create_customer", False, str(e))

    def test_intake_submit(self):
        """Test POST /intake/submit"""
        if not self.customer_id:
            self.log("intake_submit", False, "no customer_id")
            return

        try:
            resp = SESSION.post(
                f"{BASE_URL}/intake/submit",
                headers=self.headers(),
                json={
                    "is_new_customer": False,
                    "customer_id": self.customer_id,
                    "lead": {
                        "title": "Smoke Test Inquiry",
                        "source_channel": "Email",
                        "sales_stage": "New",
                        "product_category": "Fiber Laser",
                    },
                    "owner_id": self.user["id"],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self.lead_id = data.get("lead_id")
                self.log("intake_submit", True, f"lead_id={self.lead_id[:8]}...")
            else:
                self.log("intake_submit", False, f"status={resp.status_code}, {resp.text[:200]}")
        except Exception as e:
            self.log("intake_submit", False, str(e))

    def test_add_follow_up(self):
        """Test POST /leads/{id}/activities"""
        try:
            resp = SESSION.post(
                f"{BASE_URL}/leads/{self.lead_id}/activities",
                headers=self.headers(),
                json={
                    "action_type": "follow_up",
                    "method": "Email",
                    "content": "Sent initial quotation",
                    "customer_feedback": "Interested",
                    "next_action": "Call to discuss",
                    "visibility": "all",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self.log("add_follow_up", True, f"activity_id={data.get('activity_id', '?')[:8]}...")
            else:
                self.log("add_follow_up", False, f"status={resp.status_code}, {resp.text[:100]}")
        except Exception as e:
            self.log("add_follow_up", False, str(e))

    def test_create_pre_sales_task(self):
        """Test POST /leads/{id}/pre-sales-tasks"""
        try:
            resp = SESSION.post(
                f"{BASE_URL}/leads/{self.lead_id}/pre-sales-tasks",
                headers=self.headers(),
                json={
                    "assignee_id": self.user["id"],
                    "request_json": json.dumps({"type": "quotation", "products": ["1kW", "2kW"]}),
                    "due_date": "2026-05-15",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self.log("create_pre_sales_task", True, f"task_id={data.get('id', '?')[:8]}...")
            else:
                self.log("create_pre_sales_task", False, f"status={resp.status_code}, {resp.text[:100]}")
        except Exception as e:
            self.log("create_pre_sales_task", False, str(e))

    def test_list_attachments(self):
        """Test GET /leads/{id}/attachments"""
        try:
            resp = SESSION.get(
                f"{BASE_URL}/leads/{self.lead_id}/attachments",
                headers=self.headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                self.log("list_attachments", True, f"count={len(data)}")
            else:
                self.log("list_attachments", False, f"status={resp.status_code}")
        except Exception as e:
            self.log("list_attachments", False, str(e))

    def test_system_info(self):
        """Test GET /admin/system-info"""
        try:
            resp = SESSION.get(
                f"{BASE_URL}/admin/system-info",
                headers=self.headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                self.log("system_info", True, f"version={data.get('version')}")
            else:
                self.log("system_info", False, f"status={resp.status_code}")
        except Exception as e:
            self.log("system_info", False, str(e))


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m backend.tests.smoke_test <username> <password>")
        print("       (server must be running on port 8000)")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]

    # Check server is running
    try:
        SESSION.get(f"{BASE_URL}/config/fields", timeout=2)
    except requests.exceptions.ConnectionError:
        print("Error: Server not running on http://127.0.0.1:8000")
        print("Start with: uvicorn backend.app_v2:app --port 8000")
        sys.exit(1)

    test = SmokeTest(username, password)
    success = test.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
