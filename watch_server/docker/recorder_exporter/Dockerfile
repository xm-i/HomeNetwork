FROM python:3.11-alpine

RUN apk add --no-cache tzdata

WORKDIR /app

COPY exporter.py /app/exporter.py

ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Tokyo

EXPOSE 9876

CMD ["python", "/app/exporter.py"]
