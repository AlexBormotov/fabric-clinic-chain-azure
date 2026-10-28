# Dev and CI image: the same environment for `make` locally and in GitHub Actions.
# Python 3.13 and Java 21 match Fabric Runtime 2.0 (Spark 4.1, Delta 4.2).
FROM python:3.13-slim-bookworm AS dev

ARG GITLEAKS_VERSION=8.30.1
ARG ACTIONLINT_VERSION=1.7.12
ARG TERRAFORM_VERSION=1.16.6
ARG TERRAFORM_SHA256=38034b38d03096399a7a1264a14561a8029b2b496fd1f169452656e53968f1b7
ARG TFLINT_VERSION=0.64.0
ARG TFLINT_SHA256=cca9d13e2e1d7a2c627af60ff899a3c9b74212899416aeb96ec764d2ef954537
ARG TFLINT_AZURERM_VERSION=0.32.0
ARG TFLINT_AZURERM_SHA256=f1150b2dea7aef001ad07002671c75b5495f4521ddf3538ededf00896f7b0aaa

# libltdl7 and the Kerberos libraries are what mssql-python's bundled ODBC driver loads on Linux.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git make curl ca-certificates \
        libltdl7 libkrb5-3 libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
        | tar -xz -C /usr/local/bin gitleaks \
    && curl -sSfL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" \
        | tar -xz -C /usr/local/bin actionlint

# Terraform and tflint for `make tf-check`; the azurerm ruleset is baked in so tflint never downloads.
ENV TFLINT_PLUGIN_DIR=/opt/tflint/plugins
RUN cd /tmp \
    && curl -sSfLo tf.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && echo "${TERRAFORM_SHA256}  tf.zip" | sha256sum -c - \
    && python -m zipfile -e tf.zip /usr/local/bin \
    && curl -sSfLo tflint.zip "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_amd64.zip" \
    && echo "${TFLINT_SHA256}  tflint.zip" | sha256sum -c - \
    && python -m zipfile -e tflint.zip /usr/local/bin \
    && curl -sSfLo azurerm.zip "https://github.com/terraform-linters/tflint-ruleset-azurerm/releases/download/v${TFLINT_AZURERM_VERSION}/tflint-ruleset-azurerm_linux_amd64.zip" \
    && echo "${TFLINT_AZURERM_SHA256}  azurerm.zip" | sha256sum -c - \
    && dir="${TFLINT_PLUGIN_DIR}/github.com/terraform-linters/tflint-ruleset-azurerm/${TFLINT_AZURERM_VERSION}" \
    && mkdir -p "$dir" \
    && python -m zipfile -e azurerm.zip "$dir" \
    && chmod +x /usr/local/bin/terraform /usr/local/bin/tflint "$dir/tflint-ruleset-azurerm" \
    && rm -f tf.zip tflint.zip azurerm.zip

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

# Owner-only image for `terraform apply`: adds the Azure CLI for `az login`. CI never builds it.
FROM dev AS infra
ARG AZURE_CLI_VERSION=2.91.0
ENV UV_TOOL_BIN_DIR=/usr/local/bin
RUN uv tool install "azure-cli==${AZURE_CLI_VERSION}"
