FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && mkdir /state /input && chown 10001:10001 /state && chmod 700 /state
COPY smartir_agent ./smartir_agent
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "smartir_agent"]
CMD ["--file", "/input/eve.json", "--state-dir", "/state"]
