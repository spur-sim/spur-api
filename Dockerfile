FROM python:3.12-slim

WORKDIR /app

# git is needed at build time only, to install spur from its GitHub
# branch (see pyproject.toml) until a released version includes the
# structured SimEvent API (spur-sim/spur PR #98).
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY spur_api ./spur_api
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .

# No CMD/ENTRYPOINT here - docker-compose.yml sets the command per
# service (api vs worker), since both share this one image.
