# Dockerfile for netprobe_lite
# https://github.com/plaintextpackets/netprobe_lite/
FROM python:3.11-slim-bookworm

COPY requirements.txt /netprobe_lite/requirements.txt

# Install python/pip
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=on

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg iputils-ping traceroute \
    && curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | bash \
    && apt-get install -y --no-install-recommends speedtest \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -r /netprobe_lite/requirements.txt --break-system-packages

WORKDIR /netprobe_lite

ENTRYPOINT [ "/bin/bash", "./entrypoint.sh" ]
