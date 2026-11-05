# Architecture

## Components

1. Local MCP server (FastAPI, 127.0.0.1 only): JSON-RPC 2.0 at `/mcp`, health at `/health`.
2. Task controller: queue, validation, approval binding, execution orchestration.
3. SQLite persistence: tasks, approvals, audit events.
4. OpenCode adapter: real HTTP client for `opencode serve`, plus mock adapter.
5. Safety module: workspace/branch/task validation and sensitive-action blocking.

## Task lifecycle

DRAFT -> VALIDATED -> AWAITING_APPROVAL -> QUEUED -> RUNNING -> COMPLETED/FAILED/BLOCKED/CANCELLED

## Data flow (primary, Playwright)

ChatGPT (visible browser) -> task extraction -> controller -> OpenCode HTTP API -> controller -> result submission into same ChatGPT conversation.

MCP remains optional and is not configured.