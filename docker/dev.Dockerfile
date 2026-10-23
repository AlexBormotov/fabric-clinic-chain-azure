# Dev and CI image: the same environment for `make` locally and in GitHub Actions.
# Python 3.13 and Java 21 match Fabric Runtime 2.0 (Spark 4.1, Delta 4.2).
FROM python:3.13-slim-bookworm

ARG GITLEAKS_VERSION=8.30.1
ARG ACTIONLINT_VERSION=1.7.12

# libltdl7 and the Kerberos libraries are what mssql-python's bundled ODBC driver loads on Linux.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git make curl ca-certificates \
        libltdl7 libkrb5-3 libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
        | tar -xz -C /usr/local/bin gitleaks \
    && curl -sSfL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" \
        | tar -xz -C /usr/local/bin actionlint

COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /usr/local/bin/uv
COPY --from=eclipse-temurin:21-jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH

# The venv lives outside the bind-mounted repository so it never collides with a host .venv.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CACHE_DIR=/root/.cache/uv \
    UV_LINK_MODE=copy \
    IN_DEV_CONTAINER=1

RUN git config --system --add safe.directory /workspace

WORKDIR /workspace
