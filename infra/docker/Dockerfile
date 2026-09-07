FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS web
WORKDIR /src
RUN npm install --global pnpm@12.3.4
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY tools/contracts/package.json tools/contracts/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web apps/web
COPY tsconfig.json ./
COPY scripts/build-pwa.mjs scripts/build-pwa.mjs
RUN pnpm --filter @math-tutor/web build

FROM python:3.14.7-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS api
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_PYTHON_PREFERENCE=only-managed UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.12.10
WORKDIR /app/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
COPY .python-version /app/.python-version
COPY apps/api/src src
RUN uv sync --locked --no-dev --python 3.14.7 --python-preference only-managed

FROM python:3.14.7-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f
RUN groupadd --gid 10001 tutor && useradd --uid 10001 --gid tutor --create-home tutor
COPY --from=api /opt/python /opt/python
COPY --from=api /app/apps/api/.venv /app/apps/api/.venv
COPY --from=api /app/apps/api/src /app/apps/api/src
COPY apps/api/migrations /app/apps/api/migrations
COPY apps/api/alembic.ini /app/apps/api/alembic.ini
COPY --from=web /src/apps/web/dist /app/web
ENV PATH=/app/apps/api/.venv/bin:$PATH DATABASE_URL=sqlite+pysqlite:////app/data/math_tutor.sqlite3 MATH_TUTOR_DATA_DIR=/app/data PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/apps/api
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "math_tutor.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
