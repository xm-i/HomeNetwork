FROM python:3.11-alpine

WORKDIR /app

COPY exporter.py /app/exporter.py

ENV PYTHONUNBUFFERED=1

EXPOSE 9876

CMD ["python", "/app/exporter.py"]
