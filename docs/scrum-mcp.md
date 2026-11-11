# TriggerToDo Scrum MCP

The three write tools require the `fengdock:write` OAuth scope. They use the same Sprint and task
records as the TriggerToDo web app. A Story is a task linked to a Sprint.

| Tool | Arguments | Result |
| --- | --- | --- |
| `create_scrum` | Required `name`, `start_date`, `end_date`. Optional `goal` and `status` (default `draft`). | Saved Sprint with `id`, `summary`, and `items`. |
| `update_scrum` | `scrum_id` and `changes` with one or more of `name`, `goal`, `start_date`, `end_date`, `status`. | Updated Sprint in the same format. |
| `manage_scrum_items` | `scrum_id`, an ordered array of 1–100 `operations`, and `destination_scrum_id` for batches containing a move. | `scrum`, `destination_scrum` (null when omitted), and `results` in input order. Each result contains `action`, `item_id`, `list_id`, and `task_id`. |

Dates use `YYYY-MM-DD`. The start date must be on or before the end date. Sprint statuses are
`draft`, `active`, and `completed`. One Sprint can be active at a time. When updating, omit fields
to preserve their values. Set `goal`, `start_date`, or `end_date` to null to clear it.

## Backlog operations

| `action` | Required fields | Optional fields and behavior |
| --- | --- | --- |
| `add` | `list_id`, `task_id` | `points` defaults to 0. `status` defaults to the linked task's current status. |
| `create` | `title` | `list_id` defaults to the TriggerToDo Inbox. Optional `description`, `priority` (default `normal`), `points` (default 0), and `status` (default `todo`). |
| `update` | `item_id` | Supply at least one of `title`, `description`, `priority`, `points`, or `status`. Pass `description: null` to clear the task description. |
| `remove` | `item_id` | Removes the Sprint membership and preserves the task in its list. |
| `move` | `item_id` | Moves a `todo` or `doing` item to the Sprint identified by `destination_scrum_id`, preserving its item ID, task reference, points, and status. The destination must be a different Sprint in `draft` or `active` status. |

Sprint item statuses are `todo`, `doing`, and `done`. An explicitly written item status also
updates the linked task's workflow. Points are nonnegative integers. Priority uses the existing task
importance levels `low`, `normal`, and `high` and is returned as `items[].task.importance`. Title and description
edits apply to the shared task. Use `search_todos` to find task references and `list_todo_lists`
to find an existing list for a new Story.

The batch commits as one transaction and recalculates the affected Sprints' points. Adding a
task already linked to that Sprint, or moving a task already linked to the destination, returns
a conflict. Errors on individual operations identify their zero-based index. If the connection
fails during a write, query the Sprint before retrying to check whether it was saved.

## Example workflow

1. Call `list_scrums` with `{"status":"all"}`. Call `search_todos` to find existing tasks and record
   their `listId` and `taskId`.
2. Call `create_scrum` with the dates and goal.

   ```json
   {"name":"Nov 16 Sprint","goal":"Finish the backlog","start_date":"2026-11-16","end_date":"2026-11-20"}
   ```

3. Use the returned Sprint ID with `manage_scrum_items`. In this example the new Sprint ID is 42.

   ```json
   {
     "scrum_id": 42,
     "operations": [
       {"action":"add","list_id":"local-list-inbox","task_id":"existing-task-id","points":3},
       {"action":"create","title":"Review onboarding","description":"Check the first-run flow","priority":"normal","points":5}
     ]
   }
   ```

4. Edit the Story using its `item_id` from `results`. Multiple updates can share the same batch.

   ```json
   {"scrum_id":42,"operations":[{"action":"update","item_id":123,"status":"doing","priority":"high","points":8}]}
   ```

5. Call `update_scrum` to adjust Sprint metadata. If another Sprint is active, complete it before
   activating this one.

   ```json
   {"scrum_id":42,"changes":{"end_date":"2026-11-21","goal":"Review and ship onboarding","status":"active"}}
   ```

6. Call `list_scrums` with `{"scrum_id":42,"include_tasks":true}` to verify the saved Sprint and Stories.

To carry an unfinished item into Sprint 43, call `manage_scrum_items` with
`{"scrum_id":42,"destination_scrum_id":43,"operations":[{"action":"move","item_id":123}]}`.

The MCP tools call the TriggerToDo REST routes `POST /api/scrums` and `PATCH /api/scrums/{scrum_id}`.
The batch tool calls the internal `POST /internal/scrums/{scrum_id}/items` route with `operations`
and `destination_scrum_id` in the JSON body. Existing Scrum query filters and defaults are unchanged.
