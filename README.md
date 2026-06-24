# bottg

This repository is set up with a UI-building toolkit for Claude Code: the
**ui-ux-pro-max** design skill plus the **shadcn** and **magic (21st.dev)** MCP
servers.

## What's configured

| Component | Where | Notes |
| --- | --- | --- |
| `ui-ux-pro-max` skill | `.claude/skills/ui-ux-pro-max/` | Design intelligence: 50+ styles, 161 palettes, font pairings, charts, UX guidelines. Re-installed on session start (data not vendored — see below). |
| `shadcn` MCP | `.mcp.json` | shadcn/ui component search & examples. No key required. |
| `magic` MCP | `.mcp.json` | 21st.dev Magic component generator. Needs `MAGIC_API_KEY`. |

## The ui-ux-pro-max skill

The skill ships ~2MB of CSV design databases, which are **not** committed to
git. Instead `.claude/skills/install-ui-ux-pro-max.sh` downloads and installs it
from [upstream](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), and a
`SessionStart` hook (`.claude/settings.json`) runs it automatically so the skill
is present in fresh environments. To install it manually:

```bash
bash .claude/skills/install-ui-ux-pro-max.sh
```

Once installed you can query it directly, e.g.:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "fintech dashboard" --design-system
```

## MCP servers

`.mcp.json` (project scope) defines both servers. `shadcn` works out of the box.
`magic` reads its key from the `MAGIC_API_KEY` environment variable — set it in
your environment (or in your Claude Code environment's variable config) before
starting a session:

```bash
export MAGIC_API_KEY="<your-21st-dev-api-key>"
```

The key is intentionally **not** stored in the repo.
