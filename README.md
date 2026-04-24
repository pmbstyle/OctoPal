<p align="center">
   <img src="https://github.com/pmbstyle/OctoPal/blob/main/logo.png?raw=true" alt="Octapal"/>
</p>

<p align="center">
  <strong>AI AGENT THAT DON'T GET YOUR MACHINE COMPROMISED</strong>
</p>

<p align="center">
   <img src="https://img.shields.io/github/v/release/pmbstyle/Octopal">
   <img src="https://img.shields.io/github/last-commit/pmbstyle/Octopal?svg=true">
   <a href="LICENSE"><img src="https://img.shields.io/github/license/pmbstyle/Octopal?svg=true"></a>
   <a href="https://deepwiki.com/pmbstyle/Octopal"><img src="https://deepwiki.com/badge.svg"></a>
</p>

Octopal is a local multi-agent runtime for autonomous execution without giving a single long-lived process unrestricted access to your machine.

It is built around a hard split between coordination and execution:

- **Octo** is the coordinator. It holds memory, user context, policy, and decides what should happen next.
- **Workers** do the side effects. They run tools, touch files, browse the web, and return results to Octo.

That separation is the point. In many agent setups, the same process that sees your secrets also executes shell commands and follows untrusted content. Octopal keeps those concerns apart.

By default, workers use the Docker launcher and get their own disposable runtime plus a private scratch workspace.

## Table of contents

- 🧭 [Why I Built Octopal](#-why-i-built-octopal)
- 🔒 [Security model](#-security-model)
- 🪛 [What it can do](#-what-it-can-do) 
- 🚀 [Quick start](#-quick-start) 
- ✨ [Key features](#-key-features)


## 🧭 Why I Built Octopal

Projects like OpenClaw, Hermes Agent, and NanoClaw show that people want agents that actually do things, not just answer questions.

That is the part I agree with. I love smart agentic systems.

What I did not like in many agent setups was the default trust model: the same agent that can see your memory, instructions, and secrets can often also walk outside your system and take unrestricted actions.

It will be exposed to many kinds of attacks, such as prompt injection, unsafe scripts, skills, and websites whose sole purpose is to attack AI agents and gain control over them. After the original OpenClaw release, the web became a much more dangerous place for AI agents.

This can lead to sensitive data exposure, identity theft, system compromise, and generally produce a lot of issues. 

Octopal tries to make that simpler and safer to reason about.

- Octo is the brain that plans and decides
- Workers do the risky part: tools, shell, files, web, and external actions
- Workers use Docker by default, so they do not start with full access to your machine
- If a worker needs files from your main workspace, you share only the paths it actually needs

Why this is better in practice:

- **easier to trust**, because the agent doing the work is not automatically sitting on top of your whole machine
- **easier to understand**, because there is a clear line between thinking and acting
- **easier to control**, because file access is shared deliberately instead of being wide open by default

OpenClaw and Hermes Agent both support sandboxed/containerized execution, but their documented defaults still allow host-side execution in common setups. Octopal takes the opposite approach: isolation first, host-style execution only as a fallback.

NanoClaw goes in a different direction and keeps the whole system much smaller. That is a good trade if you want the leanest possible setup. Octopal is broader on purpose: memory, worker templates, channels, MCP, skills, recurring tasks, and a private gateway/dashboard all live in one runtime.

## 🔒 Security Model

Octopal is designed so the coordinator keeps the sensitive context and workers handle execution.

- Docker is the default worker runtime
- Workers keep their own private scratch workspace by default
- Sharing files from Octo's main workspace requires explicit `allowed_paths`
- Dashboard and dashboard APIs can be protected with a token and exposed remotely through Tailscale

### Why Docker workers

Docker is not here just for packaging. In Octopal, it is the default execution boundary.

Workers routinely touch untrusted inputs: web pages, external APIs, generated code, shell commands, and third-party tools. Running that work in a disposable container is a stronger default than letting the same long-lived process that holds your memory and policy also execute everything directly on the host.

It also makes the runtime easier to reason about across macOS, Linux, and Windows: the worker environment is explicit, rebuildable, and separate from your main Octo process.

## 🪛 What It Can Do

- Run as a persistent AI operator over Telegram or WhatsApp
- Plan work and delegate tasks to specialized workers
- Execute filesystem, web, browser, shell, and MCP tools under policy controls
- Create and reuse worker templates, MCP server connections, and `SKILL.md`-based skills
- Maintain persistent memory, canon, and user/system identity files
- Monitor context health and trigger structured context resets when needed
- Keep Octo prompts smaller with deferred tool loading and compact bootstrap context
- Schedule recurring tasks and background routines
- Expose a private gateway and dashboard for status, workers, and system visibility
- A set of canonical memory files shapes the system environment

See [docs/context_tool_loading.md](docs/context_tool_loading.md) for the current context and tool-loading strategy.


```
User
   │
Channels (Telegram / WhatsApp / WS)
   │
 Octo
   │
 Worker Pool
   │
 Tools / MCP / Skills
   │
 External Systems
```

**Example workflow:**

User:
"Research the latest Gemini model and write a summary."

Octo:
1. Spawns Web Researcher
2. Researcher fetches sources
3. Writer worker generates a summary
4. Octo stores canon entry
5. Result returned to the user

## 🚀 Quick Start

### Install with one line

macOS/Linux:

```bash
curl -fsSL https://octopal.ca/octopal.sh | bash
```

Windows:

```powershell
irm https://octopal.ca/octopal.ps1 | iex
```

Complete configuration in CLI. You can always change the configuration using `uv run octopal configure` command.

### Optional: WhatsApp setup

After you configure your WhatsApp number in the config link Octopal as a new device

```bash
uv run octopal whatsapp link
```

### Open the web dashboard

After bootstrap, start Octopal and then open the dashboard in your browser:

```bash
uv run octopal start
```

Open [http://127.0.0.1:8001/dashboard](http://127.0.0.1:8001/dashboard) (change to Tailscale IP for remote access)

If you enabled dashboard protection during `octopal configure`, use the `gateway.dashboard_token` value from `config.json` when the dashboard or dashboard API asks for it.

If the page says the dashboard is unavailable, build and enable the web app first:

```bash
cd webapp
npm run build
```

Then enable the dashboard bundle in `config.json` by setting `"gateway": { "webapp_enabled": true }` and start Octopal again.

<img alt="Octopal dashboard" src="https://github.com/user-attachments/assets/2ef52921-a563-41d3-a4c8-8f01faf8e93b" />

## ⚒️ Manual setup

If you do not want the bootstrap script, use the manual path below.

```bash
git clone https://github.com/pmbstyle/Octopal.git
cd Octopal
uv sync
uv run octopal configure
```

Alternative without `uv`:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -e .
```

Then run:

```bash
uv run octopal configure
```

`configure` creates or updates `config.json` and bootstraps workspace files if missing.

### Configuration model

`config.json` is the configuration file.

- `uv run octopal configure` writes the structured config there.

### Start

```bash
# background mode
uv run octopal start

# foreground mode
uv run octopal start --foreground
```

## Core Commands

```bash
uv run octopal start
uv run octopal stop
uv run octopal restart
uv run octopal status
uv run octopal update
```

## Docker Worker Launcher

Docker workers are the default and recommended runtime. You can build the worker image up front:

```bash
uv run octopal build-worker-image --tag octopal-worker:latest
```

Then set in `config.json`:

```json
{
  "workers": {
    "launcher": "docker",
    "docker_image": "octopal-worker:latest"
  }
}
```

Restart Octopal after config changes.

```bash
uv run octopal restart
```

If Docker CLI and the Docker daemon are available but the configured worker image is missing, Octopal will try to build it automatically on startup. If Docker is unavailable or the automatic build fails, Octopal will temporarily fall back to `same_env` and surface the reason in `octopal status` and the dashboard.

Workers keep their own scratch workspace by default. To share files from Octo's main workspace with a worker, pass explicit `allowed_paths`; if `allowed_paths` is omitted, the worker does not get broad workspace access.


## ✨ Key Features

### 💻 Local and Cloud deployment

Octopal can work from any environment that supports Python execution.
Fast and simple bootstrap onboarding helps you to start using Octopal right away.

- deploy on your local PC (Linux, Windows, MacOS)
- deploy on a VPS
- deploy in Docker

Octopal works from a specified directory and has no access to your system components.

### 🧠 Delegation-driven architecture

Octo, which holds all system context and sensitive data, never communicates with the outside world on its own.
Instead, the Octo delegates tasks to workers with limited context and predefined tool/skill sets.
Workers can spawn subworkers for multi-step tasks. Workers can only return response of their tasks or question/error responses. 

- Octo delegates external operations to workers, which ensures context isolation, enhances security, and provides async task execution
- workers execute in an isolated environment, which gets deleted after each execution
- workers can act as orchestrators and create sub-workers for multi-tasking
- workers operate with a predefined set of tools, MCP, and skills in their config as well as `max_thinking_steps` and `execution_timeout`
- the Octo can create new workers for a specific task (ex. use a skill to work with an external resource)
- Prebuilt worker templates include:
  - Web Researcher
  - Web Fetcher
  - Data Analyst
  - Code Worker
  - Writer
  - DevOps / Release Manager
  - Security Auditor
  - Test Runner
  - System Self-Controller
  - DB Maintainer
  - Repo Researcher
  - Bug Investigator

### 📃 Multilayer memory system

Octo operates with a local vector database to store communication history and file-based context:

- **MEMORY.md** – working memory and durable context; important facts, current state, and notes the system may need across sessions
- **memory/canon/** – curated long-term knowledge that has been reviewed and promoted into trusted reference material
- **USER.md** – user profile, preferences, habits, and interaction style
- **SOUL.md** – system identity, values, tone, and core behavioral principles
- **HEARTBEAT.md** – recurring duties, monitoring loops, schedules, and background obligations

See [docs/memory.md](docs/memory.md).

### 🤖 Multi-channel user communication

Octopal supports:
- Telegram (Botfather)
- WhatsApp (Dedicated or personal numbers)
- WS API gateway (Build or bring your own client)

Communication channels, by default, provide full support of functions like:
- text communication
- image attachments
- message reactions
- 5s grace window for user messages:

  You can send a followback message before the Octo executes it - this helps to prevent typos, wrong commands, etc.

### ⚙️ Web dashboard

The Dashboard provides a real-time, comprehensive view of the system's state, active workers, and communication logs. It is built as a modern Vite + React web application.

- **Secure by default:** Built-in token-based authentication and optional Tailscale integration.
- **Real-time updates:** Uses WebSockets for live streaming of agent thoughts and tool executions.
- **Terminal mode:** Access a live view directly from your CLI via `octopal dashboard --watch`.

### 🔒 Remote Access & Security (Tailscale)

Octopal features first-class integration with **Tailscale** to provide secure remote access without opening ports or configuring complex firewalls:

- **Automatic Tunneling:** If Tailscale is installed, Octopal can automatically run `tailscale serve` to expose the gateway to your private tailnet.
- **IP-Based Authorization:** The WebSocket and Dashboard APIs automatically verify that incoming connections originate from trusted Tailscale nodes or your local machine.
- **Easy Configuration:** Managed via `config.json` in the `gateway` section.

```json
{
  "gateway": {
    "tailscale_auto_serve": true,
    "tailscale_ips": "100.x.y.z,100.a.b.c"
  }
}
```

### 🧩 Skills and skill bundles

Octopal supports workspace-local skill bundles under `workspace/skills/<skill-id>/`.

- auto-discovers `SKILL.md` bundles
- keeps `skills/registry.json` as a compatibility layer
- supports optional `scripts/`, `references/`, and `assets/`
- exposes readiness checks for required binaries and env vars
- runs bundled scripts through a dedicated safe runner instead of raw shell
- can install external skills with ClawHub-style commands like `uv run octopal skill install <publisher>/<skill-pack>`
- also accepts direct `SKILL.md` URLs and local bundle paths
- supports installer lifecycle commands: `skill install`, `skill list`, `skill update`, `skill trust`, `skill untrust`, `skill remove`
- shows both local workspace skills and installer-managed skills in `skill list`
- requires isolated per-skill runtime envs for Python and JS/TS script-backed skills
- auto-verifies imported scripts and auto-prepares isolated envs during install/update when possible

See [docs/skills.md](docs/skills.md) for the current format and behavior.

### 🛜 Connectors (experimental)

Connectors are the integration layer between Octopal and external services. Octopal will operate with selected services on your behalf.

- **Google Connector**

   <img src="https://www.gstatic.com/images/branding/productlogos/gmail_2020q4/v11/192px.svg" height="60"> <img src="https://www.gstatic.com/images/branding/productlogos/calendar_2020q4/v13/192px.svg" height="60"> <img src="https://www.gstatic.com/images/branding/productlogos/drive_2020q4/v10/192px.svg" height="60">

   Gmail | Google Calendar | Google Drive

- **GitHub Connector**
  
  <img src="https://octopal.ca/github.png" height="60">

See [docs/connectors.md](docs/connectors.md) for more info.

## Troubleshooting

### Telegram bot starts but does not reply

- Verify `telegram.bot_token` in `config.json`
- Verify your chat ID is listed in `telegram.allowed_chat_ids`
- Check `uv run octopal status` and `uv run octopal logs --follow`

### WhatsApp is selected, but not receiving messages

- Verify `user_channel` is set to `whatsapp` in `config.json`
- Verify your phone number is listed in `whatsapp.allowed_numbers`
- Run `uv run octopal whatsapp install-bridge`
- Run `uv run octopal whatsapp link`
- Start Octopal again and check `uv run octopal whatsapp status`

### LLM errors

- Run `uv run octopal configure` and pick the provider you want to use.
- In your config file, check `llm.provider_id`, `llm.model`, and `llm.api_key` in `config.json`.

### Web search/fetch issues

Add the preferred search engine API key in your `config.json`

```json
"search": {
    "brave_api_key": null,
    "firecrawl_api_key": null
},
```

