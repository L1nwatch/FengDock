# TriggerToDo tasks through FengDock MCP

The three Todo write tools require `fengdock:write` alongside `fengdock:read`. Use `list_todo_lists` to locate a list and `search_todos` with `include_details: true` to verify saved task information. Task search returns `listId` and `taskId`. Pass those values as `list_id` and `task_id` to the write tools.

## Create a task

`create_todo` requires `title`. Omit `list_id` to use Inbox. An explicit list ID must exist. The remaining inputs are optional.

| Input | Accepted values |
| --- | --- |
| `description` | Task notes |
| `priority` | `low`, `normal` (default), or `high` |
| `trigger_type` | `none` (default), `date`, `date:daily`, `date:weekly`, `date:monthly`, or `date:yearly` |
| `due_at` | RFC3339 timestamp with an explicit offset or `Z`. Required for a date trigger |
| `timezone` | IANA time zone for the schedule, defaulting to `UTC`. The offset in `due_at` identifies the instant |
| `recurrence_interval` | Positive integer for recurring date triggers, defaulting to 1 |
| `workflow_status` | `wait-for-trigger`, `todo`, or `doing`. Defaults to `wait-for-trigger` for date triggers and `todo` for other tasks |
| `epic_key`, `pool` | Optional TriggerToDo metadata |
| `idempotency_key` | A client-generated identifier, such as a UUID, reused for retries of the same creation in the same list |

For example, this creates a one-time task at 19:00 in Toronto on February 8, 2027. The response reports `due_at: "2027-02-09T00:00:00Z"`, `timezone: "America/Toronto"`, `trigger_ref: "date"`, and `recurrence: null`, alongside the persisted task and list IDs.

```json
{
  "title": "增肌实验 12 周复盘",
  "description": "检查左右上臂围度、训练照片、弹力带阻力、训练次数、组数、频率及 Level 变化，并评估肩背恢复情况。",
  "due_at": "2027-02-08T19:00:00-05:00",
  "timezone": "America/Toronto",
  "trigger_type": "date"
}
```

Creation leaves Sprint membership unset. Use `manage_scrum_items` to explicitly add a task to a Sprint.

MCP sends each write once. If the connection drops, use `search_todos` to check whether it committed. Resubmitting the same creation with its original key returns the existing task. Reusing the same key for different task data in the same list returns a conflict. Unkeyed creation calls are independent.

## Update and complete

`update_todo` takes `list_id`, `task_id`, and `changes`. Supply only the fields to edit. It accepts the editable creation fields and `task_status` (`notStarted`, `inProgress`, `completed`, `waitingOnOthers`, or `deferred`). It returns the complete saved task.

- Use `null` to clear optional fields. Clearing `timezone` resets it to UTC when the task has a deadline. Clearing `recurrence_interval` resets an existing repeat interval to 1.
- To remove the date trigger and recurrence, set `trigger_type` to `none` or `null`. Include `due_at: null` to remove the deadline as well.
- Rescheduling without changing the trigger or interval preserves the recurrence configuration. A timezone-only update preserves the current scheduled instant and uses the new timezone for later occurrences.

`complete_todo` takes the same IDs and returns `task`, `already_completed`, and `next_task`. A recurring task produces one successor. Retrying completion of the same occurrence returns the existing successor while it is available. A one-time task returns `next_task: null`.

Date repeats follow the scheduled local calendar time and skip past occurrences. Monthly and yearly repeats use the last day of short months when the anchored day is unavailable. During the spring DST gap, the affected occurrence moves forward by the gap and later occurrences resume the anchored local time.

## What happens when a date arrives

The current `/today` route opens the Trigger Set Board. The board shows future date triggers under **Pending Trigger** and reevaluates the time while open. A due task with workflow status `wait-for-trigger` moves to the **todo** column in the browser. Reload the board to fetch changes made through MCP or another browser. Completed and deleted tasks are excluded.

Time passing leaves persisted `workflow_status` unchanged. A deadline without a configured trigger stays a deadline. Date triggers control board visibility and send no notifications or push alerts.
