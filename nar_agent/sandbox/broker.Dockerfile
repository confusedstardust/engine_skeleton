FROM python:3.13-slim
WORKDIR /srv/broker
RUN pip install --no-cache-dir fastapi==0.162.0 uvicorn==0.54.0 docker==7.1.0
COPY sandbox/broker.py ./broker.py
CMD ["python", "-m", "uvicorn", "broker:app", "--host", "0.0.0.0", "--port", "8030", "--workers", "1"]
