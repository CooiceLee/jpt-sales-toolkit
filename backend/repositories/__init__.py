"""
Repository layer - database access abstraction.

Repositories handle all direct database operations and provide
a clean interface for services. This layer enables future migration
from SQLite to other databases.
"""

from .base import BaseRepository, close_db, get_db, get_transaction, init_db
from .user_repository import UserRepository
from .customer_repository import CustomerRepository
from .customer_alias_repository import CustomerAliasRepository
from .lead_repository import LeadRepository
from .activity_repository import ActivityRepository
from .task_repository import PreSalesTaskRepository, AfterSalesTaskRepository
from .attachment_repository import AttachmentRepository
from .audit_repository import AuditRepository
from .data_quality_issue_repository import DataQualityIssueRepository
from .authorization_event_repository import AuthorizationEventRepository
from .device_authorization_repository import DeviceAuthorizationRepository
from .organization_repository import OrganizationRepository
from .user_credential_repository import UserCredentialRepository

__all__ = [
    "BaseRepository",
    "close_db",
    "get_db",
    "get_transaction",
    "init_db",
    "UserRepository",
    "CustomerRepository",
    "CustomerAliasRepository",
    "LeadRepository",
    "ActivityRepository",
    "PreSalesTaskRepository",
    "AfterSalesTaskRepository",
    "AttachmentRepository",
    "AuditRepository",
    "DataQualityIssueRepository",
    "OrganizationRepository",
    "UserCredentialRepository",
    "DeviceAuthorizationRepository",
    "AuthorizationEventRepository",
]
