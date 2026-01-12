FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        python3 \
        zstd \
    && rm -rf /var/lib/apt/lists/*

ENV ELAN_HOME=/root/.elan
ENV PATH="$ELAN_HOME/bin:$PATH"

RUN curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y

WORKDIR /repo
COPY . /repo

RUN elan toolchain install "$(cat lean-toolchain)"

RUN python3 tools/policy/check_repo.py \
    && bash tools/lean/audit_no_sorry.sh \
    && bash tools/lean/audit_no_axiom.sh \
    && bash tools/lean/audit_no_unsafe.sh \
    && lake exe cache get \
    && lake build
