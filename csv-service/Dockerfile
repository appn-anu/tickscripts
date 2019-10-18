FROM python:3.8.0-alpine3.10

# need to add tzdata for correct timezone stuff.
RUN apk add --no-cache tzdata && rm -rf /var/cache/apk/*

ENV PYTHONUNBUFFERED=1

COPY . .

ENV OUTPUT_DIR "default"
EXPOSE 9999

CMD ["python3", "run.py"]
