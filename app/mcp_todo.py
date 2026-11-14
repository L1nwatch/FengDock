"""FengDock MCP models for TriggerToDo tasks."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StrictStr, StringConstraints, model_validator

from vendor.TriggerToDo.app.todo_contract import DateScheduleChanges

TodoId = Annotated[str, Field(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-][A-Za-z0-9._=+~-]*$")]
TodoTitle = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1024)]
TodoLabel = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)]
Priority = Literal["low", "normal", "high"]
WorkflowStatus = Literal["wait-for-trigger", "todo", "doing"]
TaskStatus = Literal["notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"]


class TodoChanges(DateScheduleChanges):
    title: TodoTitle | None = None
    description: StrictStr | None = None
    priority: Priority | None = None
    workflow_status: WorkflowStatus | None = None
    epic_key: TodoLabel | None = None
    pool: TodoLabel | None = None
    task_status: TaskStatus | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one change is required")
        for name in ("title", "task_status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be cleared")
        return self

    def to_rest_patch(self) -> dict[str, Any]:
        fields = self.model_dump(exclude_unset=True)
        payload = {}
        direct_fields = {"title": "title", "priority": "importance", "task_status": "status"}
        for name, destination in direct_fields.items():
            if name in fields:
                payload[destination] = fields[name]
        if "description" in fields:
            content = fields["description"]
            payload["body"] = {"contentType": "text", "content": content} if content is not None else None
        schedule = {name: fields[name] for name in DateScheduleChanges.model_fields if name in fields}
        if schedule:
            payload["date_schedule"] = schedule
        extension_fields = {"workflow_status": "wfStatus", "epic_key": "epicKey", "pool": "pool"}
        extensions = {destination: fields[name] for name, destination in extension_fields.items() if name in fields}
        if extensions:
            payload["extensions"] = extensions
        return payload


class TodoState(BaseModel):
    list_id: str
    task_id: str
    title: str
    description: str
    priority: str | None
    task_status: str | None
    due_at: str | None
    timezone: str | None
    trigger_ref: str | None
    recurrence: dict[str, Any] | None
    workflow_status: str | None
    epic_key: str | None
    pool: str | None
    source: str | None
    created_at: str | None
    updated_at: str | None

    @classmethod
    def from_rest(cls, task: dict[str, Any]) -> "TodoState":
        due = task.get("dueDateTime") or {}
        metadata = next(
            (ext for ext in task.get("extensions", []) if ext.get("extensionName") == "com.triggertodo.meta"),
            {},
        )
        return cls(
            list_id=task["listId"], task_id=task["id"], title=task["title"],
            description=(task.get("body") or {}).get("content") or "",
            priority=task.get("importance"), task_status=task.get("status"),
            due_at=due.get("dateTime"), timezone=due.get("timeZone"), recurrence=task.get("recurrence"),
            trigger_ref=metadata.get("triggerRef"), workflow_status=metadata.get("wfStatus"),
            epic_key=metadata.get("epicKey"), pool=metadata.get("pool"), source=metadata.get("source"),
            created_at=task.get("createdDateTime"), updated_at=task.get("lastModifiedDateTime"),
        )


class TodoCompletion(BaseModel):
    task: TodoState
    already_completed: bool
    next_task: TodoState | None
