FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config ./config
RUN mkdir -p /app/data && chown -R app:app /app

USER app
ENTRYPOINT ["chat-discovery"]
CMD ["--help"]

FROM runtime AS test
USER root
COPY scripts ./scripts
COPY tests ./tests
RUN pip install --no-cache-dir ".[dev]" && python -m pytest

FROM runtime AS final
