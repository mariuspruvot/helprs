# node 20 reached end of life in April 2026, on the one image that executes
# untrusted PR content. The web build is already on 22.
FROM node:22-slim

# Pinned deliberately. The whole SSE pipeline parses this CLI's stream-json
# output -- the five event types in CLAUDE.md are its contract, not ours -- so
# an upstream format change would break production on the next image rebuild,
# with no code change and nothing in CI to catch it. Bump this on purpose,
# then re-run a session end to end.
ARG CLAUDE_CODE_VERSION=2.1.220

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        jq && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && \
    apt-get install -y --no-install-recommends gh && \
    npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash runner

WORKDIR /workspace

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown runner:runner /workspace

USER runner
ENTRYPOINT ["/entrypoint.sh"]
