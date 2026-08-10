"""
Router layer - FastAPI route definitions.

Routers define HTTP endpoints and delegate to services.
"""

from .auth import router as auth_router
from .configuration import router as config_router
from .customers import router as customers_router
from .leads import router as leads_router
from .intake import router as intake_router
from .tasks import router as tasks_router
from .review import router as review_router
from .admin import router as admin_router
from .data_exchange import router as data_exchange_router
from .authorization import router as authorization_router
from .desktop import router as desktop_router
from .spreadsheet_import import router as spreadsheet_import_router
from .data_quality_issues import router as data_quality_issues_router
from .inquiry_aggregate import router as inquiry_aggregate_router
from .tech_task_exchange import router as tech_task_exchange_router

__all__ = [
    "auth_router",
    "config_router",
    "customers_router",
    "leads_router",
    "intake_router",
    "tasks_router",
    "review_router",
    "admin_router",
    "data_exchange_router",
    "authorization_router",
    "desktop_router",
    "spreadsheet_import_router",
    "data_quality_issues_router",
    "inquiry_aggregate_router",
    "tech_task_exchange_router",
]
