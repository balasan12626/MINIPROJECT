---
name: backend
description: Use when working on server-side logic, services, routes, validation, authentication, or backend business logic.
---

# Backend Workflow

- Inspect only the relevant FastAPI/backend files.
- Follow existing router, service, and middleware patterns.
- Reuse current services and utilities before adding new ones.
- Preserve API contracts unless a change is explicitly required.
- Validate inputs at service boundaries.
- Handle errors consistently with project conventions.
- Avoid unnecessary dependencies.
- Test the smallest relevant endpoint/service first.
