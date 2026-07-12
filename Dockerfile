FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY README.md .
COPY src/ src/

# Install without Playwright — only need lxml + pydantic + fastapi + uvicorn
RUN pip install --no-cache-dir lxml pydantic fastapi uvicorn && \
    pip install --no-cache-dir --no-deps -e .

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "schemasnap.server:app", "--host", "0.0.0.0", "--port", "8080"]
