FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY edth_node ./edth_node
RUN pip install .

ENTRYPOINT ["python", "-m", "edth_node"]
