FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY scenarios ./scenarios
RUN pip install --no-cache-dir .

RUN useradd -m -u 10001 appuser
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8583

ENTRYPOINT ["iso-checker"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8583", "--scenario-file", "/app/scenarios/default.yaml"]
