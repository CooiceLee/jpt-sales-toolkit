"""Request models shared by task route modules."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TaskListFilters(BaseModel):
    limit: int = 100
    offset: int = 0
    lead_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[str] = None
    include_archived: bool = False


class PreSalesTaskCreate(BaseModel):
    assignee_id: Optional[str] = None
    client_request_id: Optional[str] = Field(default=None, max_length=128)
    status: Optional[Literal["Open", "In Progress", "Completed", "Cancelled"]] = None
    request_json: Optional[str] = None
    result_json: Optional[str] = None
    due_date: Optional[str] = None


class PreSalesTaskUpdate(BaseModel):
    assignee_id: Optional[str] = None
    status: Optional[Literal["Open", "In Progress", "Completed", "Cancelled"]] = None
    request_json: Optional[str] = None
    result_json: Optional[str] = None
    due_date: Optional[str] = None
    row_version: int


# The four the form offers and the database accepts. Typed as free text here,
# an unknown value travelled all the way to the CHECK constraint and came back
# as a 500 - a server fault for what is a rejected input.
AfterSalesIssueType = Literal["Technical", "Quality", "Delivery", "Other"]
AfterSalesStatus = Literal["Open", "In Progress", "Resolved", "Closed"]


class AfterSalesTaskCreate(BaseModel):
    assignee_id: Optional[str] = None
    issue_type: AfterSalesIssueType
    issue_description: str
    status: Optional[AfterSalesStatus] = None
    solution: Optional[str] = None
    customer_satisfaction: Optional[str] = None
    lessons_learned: Optional[str] = None
    remarks: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[str] = None


class AfterSalesTaskUpdate(BaseModel):
    assignee_id: Optional[str] = None
    issue_type: Optional[AfterSalesIssueType] = None
    issue_description: Optional[str] = None
    status: Optional[AfterSalesStatus] = None
    solution: Optional[str] = None
    customer_satisfaction: Optional[str] = None
    lessons_learned: Optional[str] = None
    remarks: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[str] = None
    row_version: int
