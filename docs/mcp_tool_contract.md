# MCP Tool Contract

Tools exposed (narrowly scoped):

- `submit_task`: task (string, required), metadata (object), workspace (string), timeout_seconds (number), idempotency_key (string). Returns execution ID; task awaits approval.
- `approve_task`: task_id (string, required), approved_by (string).
- `reject_task`: task_id (string, required), reason (string).
- `get_task_status`: task_id (string, required).
- `get_task_result`: task_id (string, required).
- `list_recent_tasks`: limit (integer, default 20).
- `cancel_task`: task_id (string, required), reason (string).

No arbitrary shell, filesystem, process or repository-management tools are exposed.