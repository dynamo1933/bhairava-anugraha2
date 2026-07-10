---
description: System instructions and engineering best practices for generating clean, readable, and modular code.
---

# AI Coding Guidelines

## Objective
Generate production-ready, clean, maintainable, and scalable code that follows software engineering best practices.

# AI Coding Guidelines

## Objective

Generate production-ready, clean, maintainable, and scalable code that follows software engineering best practices.

---

# General Principles

- Always prioritize readability over cleverness.
- Write code as if another engineer will maintain it for the next five years.
- Avoid unnecessary complexity.
- Prefer explicit code over implicit behavior.
- Follow SOLID principles whenever applicable.
- Follow DRY (Don't Repeat Yourself).
- Follow KISS (Keep It Simple).
- Follow YAGNI (You Aren't Gonna Need It).

---

# Project Structure

Organize the project into logical modules.

Example:

```
project/
│
├── app/
│   ├── api/
│   ├── services/
│   ├── models/
│   ├── repositories/
│   ├── agents/
│   ├── prompts/
│   ├── utils/
│   ├── config/
│   ├── constants/
│   ├── exceptions/
│   └── schemas/
│
├── tests/
├── docs/
├── scripts/
├── data/
├── examples/
└── main.py
```

Never place all logic inside one file.

---

# File Size

Keep files small.

Preferred:

- under 300 lines

Maximum:

- 500 lines

If a file grows larger:

- split into modules
- extract helper functions
- create service classes

---

# Function Design

Functions should:

- do one thing only
- be easy to understand
- have descriptive names

Preferred length:

- under 40 lines

Maximum:

- 60 lines

Avoid deeply nested logic.

Use early returns.

Instead of:

```
if ...
    if ...
        if ...
```

Prefer:

```
if invalid:
    return

...
```

---

# Class Design

Each class should have a single responsibility.

Avoid "God Classes".

If a class exceeds roughly:

- 300-400 lines

consider splitting it.

---

# Naming Convention

Use meaningful names.

Good:

```
calculate_customer_margin()

load_policy_documents()

build_vector_index()

validate_request()
```

Avoid:

```
func1()

helper()

temp()

data2()
```

---

# Variable Names

Variables should clearly describe their purpose.

Good:

```
customer_transactions

monthly_margin

policy_documents
```

Avoid:

```
x

tmp

abc

list1
```

---

# Comments

Only write comments that explain *why*.

Do not explain obvious code.

Bad:

```
# increment i
i += 1
```

Good:

```
# Retry once because the upstream API occasionally returns transient failures.
```

---

# Docstrings

Every public function should contain a docstring.

Example:

```python
def calculate_margin(account):
    """
    Calculate the expected monthly margin for an account.

    Args:
        account: Customer account object.

    Returns:
        Estimated monthly margin.
    """
```

---

# Type Hints

Always use type hints.

Example:

```python
def calculate_score(
    bureau_data: pd.DataFrame,
) -> float:
```

Avoid untyped functions.

---

# Error Handling

Never silently ignore exceptions.

Bad:

```python
try:
    ...
except:
    pass
```

Good:

```python
try:
    ...
except ValidationError as ex:
    logger.exception(ex)
    raise
```

Catch specific exceptions.

---

# Logging

Never use print().

Use logging.

Example:

```python
logger.info()

logger.warning()

logger.error()

logger.exception()
```

Log:

- important events
- failures
- retries
- API calls
- execution time

Do not log secrets.

---

# Configuration

Never hardcode:

- API Keys
- URLs
- Passwords
- Model names
- File paths

Use:

- .env
- config.py
- YAML
- JSON

---

# Constants

Store constants separately.

Example:

```
constants.py
```

```
DEFAULT_TIMEOUT = 30

MAX_RETRIES = 3
```

Avoid magic numbers.

---

# Modularization

Separate responsibilities.

Instead of:

```
main.py

- API
- Database
- Prompt
- LLM
- Parsing
- Validation
```

Use:

```
api/

database/

agents/

prompts/

parser/

validator/

services/
```

---

# Reusability

Avoid duplicate logic.

Extract reusable functions.

Prefer composition over duplication.

---

# Dependency Injection

Avoid creating dependencies inside business logic.

Instead of:

```
client = AzureChatOpenAI(...)
```

Inject:

```
def __init__(self, llm):
```

This improves testing.

---

# Testing

Write testable code.

Business logic should not depend directly on:

- UI
- Flask
- FastAPI
- Streamlit

Keep business logic separate.

---

# LLM Code

Separate:

- prompt templates
- output parsers
- model configuration
- chains
- agents
- tools

Do not embed prompts inside business logic.

Use dedicated prompt files.

---

# Prompt Engineering

Store prompts in:

```
prompts/

    summarizer.md

    planner.md

    sql_generator.md
```

Avoid hardcoded multiline prompts.

---

# Agent Design

Each agent should have a single responsibility.

Example:

```
PlannerAgent

RetrieverAgent

SQLAgent

ValidatorAgent

FormatterAgent

ReportAgent
```

Do not create one agent that performs everything.

---

# API Design

Routes should be thin.

Bad:

```
Route

↓

Validation

↓

Business Logic

↓

Database

↓

LLM

↓

Formatting
```

Good:

```
Route

↓

Service

↓

Repository

↓

LLM Client
```

---

# Repository Pattern

Database access belongs in repositories.

Business logic belongs in services.

Do not mix them.

---

# Performance

Avoid:

- repeated API calls
- repeated database queries
- repeated vector searches

Cache when appropriate.

Batch operations whenever possible.

---

# Async

Use async only when it improves performance.

Do not overuse asynchronous programming.

---

# Security

Never:

- expose API keys
- log secrets
- disable SSL verification
- trust user input

Always validate inputs.

---

# Formatting

Use:

- Black
- Ruff
- isort

Follow PEP 8.

Maximum line length:

88-100 characters.

---

# Imports

Order imports as:

1. Standard library

2. Third-party libraries

3. Local modules

Example:

```python
import os

import pandas as pd

from app.services import MarginService
```

---

# Folder Responsibilities

api/
- endpoints only

services/
- business logic

repositories/
- database access

agents/
- LLM agents

prompts/
- prompt templates

utils/
- generic reusable utilities

config/
- configuration

models/
- ORM models

schemas/
- Pydantic models

tests/
- unit/integration tests

---

# Code Review Checklist

Before completing any task, verify:

- Code is readable.
- Functions have a single responsibility.
- Classes have a single responsibility.
- No duplicated logic.
- Proper logging added.
- Type hints included.
- Docstrings added.
- Exceptions handled correctly.
- Constants extracted.
- Configuration externalized.
- Imports cleaned.
- Unused code removed.
- Files remain modular.
- Tests updated if required.
- Naming is descriptive.
- Prompt templates separated from logic.
- Business logic is independent of framework code.

---

# Expected Code Quality

Always generate code that is:

- Production-ready
- Readable
- Modular
- Reusable
- Testable
- Extensible
- Well documented
- Secure
- Efficient
- Easy to review
- Easy to debug
- Easy to maintain

Prefer clean architecture over quick fixes.

If implementing a new feature would make an existing file or class too large or violate these guidelines, refactor the relevant code into smaller modules before adding the feature.