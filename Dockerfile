FROM python:3.12-slim-bookworm

WORKDIR /app

# git: clone/worktree; bubblewrap/socat/rg: Slice 5.6a SRT-style strong sandbox canaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    bubblewrap \
    socat \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY config ./config
COPY src ./src
# AgentFacts-lite (V5 T01): human + machine cards + signed manifest for agentctl agentfacts check
COPY agent-card.json agent-facts.json ./
COPY docs/AGENT_CARD.md ./docs/AGENT_CARD.md

RUN pip install --no-cache-dir -e ".[dev]"
# In-image Semgrep CE FACT PRODUCER (pinned). Distinct process + sanitized env.
# Always-on compose must not grow docker.sock; runner prefers this local binary.
# setuptools<81 keeps pkg_resources for Semgrep 1.110.0 otel instrumentation on Py3.12.
RUN pip install --no-cache-dir semgrep==1.110.0 "setuptools<81" \
    && SEMGREP_SEND_METRICS=off semgrep --version 2>&1 | grep -F "1.110.0"

EXPOSE 8080

CMD ["agentctl", "webhook", "serve", "--host", "0.0.0.0", "--port", "8080"]
