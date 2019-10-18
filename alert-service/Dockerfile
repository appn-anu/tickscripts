FROM alpine:latest

RUN apk add --no-cache \
    tzdata \
    python3 \
    py3-pip \
    py3-yaml \
 && pip3 install requests PyGithub slackclient \
 && rm -rf /var/cache/apk/*
ENV PYTHONUNBUFFERED=1

COPY . .

ENV GITHUB_API_TOKEN ""
ENV GITHUB_ORG ""
ENV GITHUB_REPO ""
ENV SCHEDULE_YAML_URL ""
ENV SLACK_API_TOKEN ""

EXPOSE 9999

CMD ["python3", "run.py"]
