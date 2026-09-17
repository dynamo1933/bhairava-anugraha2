---
description: Mandatory workflow to maintain and consult gemini_change.log across all coding sessions.
alwaysApply: true
---

# Change Log Protocol (`gemini_change.log`)

## 1. Start of Session (MANDATORY)
At the start of EVERY new session or user task, you MUST view/read `gemini_change.log`:
- Obtain a summary of the latest changes, current active database state, and architectural context.
- Ensure you do not regress recent fixes or misunderstand current implementation details.

## 2. End of Session (MANDATORY)
Before finishing any session where files or database records were modified, you MUST append a new entry to `gemini_change.log` containing:
- **Timestamp**: Date & Time (ISO or local with timezone)
- **Objective**: The user's request and goal of the session
- **Files Modified / Created / Deleted**: Explicit list of files touched
- **Summary of Changes**: Key technical decisions, regexes, schema updates, or fixes implemented
- **Verification & Testing**: Commands run, test outputs, or browser verification steps performed
