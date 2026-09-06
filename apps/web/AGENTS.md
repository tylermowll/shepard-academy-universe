# Frontend instructions

Read the root AGENTS.md and current task first. Keep this a client-rendered
React/TypeScript/Vite app. Use semantic HTML and local assets; add libraries only
when a working feature needs them.

- Backend schemas and services own validation, authorization, and grading.
- Before the first API-consuming feature, generate frontend types from FastAPI
  OpenAPI and add a regeneration drift check. Do not hand-maintain API schemas.
- No provider keys, answer keys, private endpoints, or administrator data in the
  frontend bundle. Never put session tokens in localStorage.
- No service worker or sensitive response caching until its explicit task.
- Add accessible labels, keyboard behavior, honest errors, and relevant component
  tests. Use browser tests for workflows and connection/retry behavior.
- Run root Make targets; `make check` includes frontend checks. `make smoke`
  builds and launches isolated loopback servers, then runs browser tests.
