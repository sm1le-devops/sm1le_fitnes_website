FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "poetry>=2.1,<3"

RUN poetry config virtualenvs.create false \
    && poetry install \
        --no-root \
        --only main \
        --no-interaction \
        --no-ansi

COPY . .

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["sh", "/app/start.sh"]