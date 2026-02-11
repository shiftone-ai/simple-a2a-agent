# simple-a2a-agent

A minimal A2A-compatible agent server powered by `pydantic-ai`.

## Run with LM Studio (OpenAI-compatible)

```bash
export SIMPLE_A2A_PROVIDER=openai
export SIMPLE_A2A_MODEL=qwen/qwen3-coder-next
export SIMPLE_A2A_BASE_URL=http://127.0.0.1:1234/v1
# SIMPLE_A2A_API_KEY is optional for openai provider

uv run python -m simple_a2a_agent
```

## Send Message To Another A2A Agent (Client Mode)

```bash
uv run python -m simple_a2a_agent client \
  --agent-url http://127.0.0.1:9000 \
  --message "Hello from this agent"
```

You can also set a default remote URL:

```bash
export SIMPLE_A2A_REMOTE_URL=http://127.0.0.1:9000
uv run python -m simple_a2a_agent client --message "Hello from this agent"
```

## Autonomous Peer Discovery + Outreach

You can trigger an agent to discover other agents (via Agent Card checks) and proactively contact them.

Set shared discovery candidates for all agents:

```bash
export SIMPLE_A2A_DISCOVERY_URLS=http://127.0.0.1:8001,http://127.0.0.1:8002
```

Run two agents with distinct names and ports:

```bash
# Terminal 1
export SIMPLE_A2A_AGENT_NAME="Agent A"
export A2A_PORT=8001
uv run python -m simple_a2a_agent serve

# Terminal 2
export SIMPLE_A2A_AGENT_NAME="Agent B"
export A2A_PORT=8002
uv run python -m simple_a2a_agent serve
```

Trigger autonomous outreach from one side:

```bash
uv run python -m simple_a2a_agent client \
  --agent-url http://127.0.0.1:8001 \
  --message "他のagentに挨拶してみてください"
```

The target agent will:

- discover reachable peers from `SIMPLE_A2A_DISCOVERY_URLS` using A2A Agent Cards
- send an autonomous relay message to each discovered peer
- return a summary including discovered peers and peer responses

## Run with LM Studio (Anthropic-compatible)

```bash
export SIMPLE_A2A_PROVIDER=anthropic
export SIMPLE_A2A_MODEL=qwen/qwen3-coder-next
export SIMPLE_A2A_BASE_URL=http://127.0.0.1:1234
export SIMPLE_A2A_API_KEY=any-non-empty-value

uv run python -m simple_a2a_agent
```

## Environment Variables

- `SIMPLE_A2A_PROVIDER` (required): `openai` or `anthropic`
- `SIMPLE_A2A_MODEL` (required): model name served by your endpoint
- `SIMPLE_A2A_BASE_URL` (required): provider base URL
- `SIMPLE_A2A_API_KEY` (required for `anthropic`, optional for `openai`)
- `SIMPLE_A2A_AGENT_NAME` (optional): Agent name exposed in Agent Card
- `SIMPLE_A2A_AGENT_DESCRIPTION` (optional): Agent description exposed in Agent Card
- `SIMPLE_A2A_PUBLIC_URL` (optional): Public URL exposed in Agent Card
- `SIMPLE_A2A_REMOTE_URL` (optional): default URL for `client` mode target agent
- `SIMPLE_A2A_DISCOVERY_URLS` (optional): comma-separated candidate A2A URLs for peer discovery
- `SIMPLE_A2A_AUTONOMOUS_HOPS` (optional): max relay hops for autonomous outreach, default `1`
- `SIMPLE_A2A_AUTONOMOUS_TIMEOUT` (optional): timeout seconds for discovery + relay requests, default `20`
- `SIMPLE_A2A_SELF_URL` (optional): override self URL used by autonomous relay logic
- `A2A_HOST` (optional): server host, default `127.0.0.1`
- `A2A_PORT` (optional): server port, default `8000`

## Nix Cache (Cachix + GitHub Actions)

This repo includes `.github/workflows/nix-cache.yml` for Nix/devenv CI with optional Cachix push.

Enable it with:

```bash
# 1) Create a Cachix cache (example name: simple-a2a-agent)
#    https://app.cachix.org/

# 2) Set cache name as a GitHub Actions variable
gh variable set CACHIX_CACHE_NAME -R shiftone-ai/simple-a2a-agent -b simple-a2a-agent

# 3) Create a write token in Cachix and register it as a GitHub secret
gh secret set CACHIX_AUTH_TOKEN -R shiftone-ai/simple-a2a-agent -b "<your-cachix-auth-token>"
```

Notes:

- Public GitHub repos can use Cachix without issue.
- Public/private is controlled independently for GitHub repo and Cachix cache.
- For forked PRs, GitHub does not expose secrets, so workflow runs in read-only cache mode.

## Startup Errors

The server fails fast on invalid configuration, for example:

- missing required variables (`SIMPLE_A2A_PROVIDER`, `SIMPLE_A2A_MODEL`, `SIMPLE_A2A_BASE_URL`)
- unsupported provider value
- missing `SIMPLE_A2A_API_KEY` when `SIMPLE_A2A_PROVIDER=anthropic`
