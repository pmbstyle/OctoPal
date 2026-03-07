# HEARTBEAT - Scheduled Tasks

This file defines recurring checks and proactive tasks.
Keep entries concrete, bounded, and easy to verify.
It is a living document and may be edited freely as schedules and routines change.

## How To Use

- Each task should have a stable ID.
- Say what should run, how often, and what output is expected.
- Prefer writing results to workspace files instead of keeping them only in chat.
- If a task depends on network access, assign an appropriate worker.
- If nothing is due, return `HEARTBEAT_OK`.

## Task Template

### Example Task
- **ID**: example_task
- **Description**: Brief description of what this task is for
- **Frequency**: Daily at 09:00
- **Worker**: web_researcher
- **Task**: [Scheduled: example_task] Do the bounded recurring work and save results to an agreed file
- **Last execution**: never
- **Status**: Disabled

## Tracking

- example_task_last_run: never
