"""Request models shared by task route modules."""

from typing import Optional

from pydantic import BaseModel


class TaskListFilters(BaseModel):
    limit: int = 100
    offset: int = 0
    lead_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[str] = None
    include_archived: bool = False


class PreSalesTaskCreate(BaseModel):
    assignee_id: Optional[str] = None
    request_json: Optional[str] = None
    due_date: Optional[str] = None


class PreSalesTaskUpdate(BaseModel):
    assignee_id: Optional[str] = None
    status: Optional[str] = None
    request_json: Optional[str] = None
    result_json: Optional[str] = None
    due_date: Optional[str] = None
    row_version: int


class AfterSalesTaskCreate(BaseModel):
    assignee_id: Optional[str] = None
    issue_type: str
    issue_description: str
    status: Optional[str] = None
    solution: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[str] = None


class AfterSalesTaskUpdate(BaseModel):
    assignee_id: Optional[str] = None
    issue_type: Optional[str] = None
    issue_description: Optional[str] = None
    status: Optional[str] = None
    solution: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[str] = None
    row_version: int
