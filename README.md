# HarnessXGate

**Free AI multi-engine router, live web dashboard, and MCP server — zero dependencies, one command to install.**

Built so anyone (even without an expensive AI subscription) can combine free AI engines (**OpenCode**, **GitHub Copilot CLI**, **FreeLLMAPI / OpenAI-compatible APIs**, and **Ollama**) behind one simple web page, one CLI (`hxg`), and one MCP tool. When one model hits a rate limit or goes offline, HarnessXGate automatically switches to the next best free model without stopping your work.

---

## One-Command Install (Opens the Web App Automatically)

### Windows — Command Prompt (`cmd`)
```cmd
curl -fsSL https://raw.githubusercontent.com/Eli-Mira/HarnessXGate/main/install.cmd -o "%TEMP%\hxg.cmd" && "%TEMP%\hxg.cmd"
```

### Windows — PowerShell
```powershell
irm https://raw.githubusercontent.com/Eli-Mira/HarnessXGate/main/install.ps1 | iex
```

### macOS / Linux / WSL
```bash
curl -fsSL https://raw.githubusercontent.com/Eli-Mira/HarnessXGate/main/install.sh | bash
```

### Or via `pip`
```bash
pip install git+https://github.com/Eli-Mira/HarnessXGate.git
hxg
```

> **Requirements:** Only **Python 3.10+** (zero extra `pip` packages needed!).

---

## How to Use (For Beginners — 30 Seconds)

1. **Open the Dashboard:** Type `hxg` in your terminal (opens `http://127.0.0.1:7878` in your browser).
2. **Check Your Engines:** You only need **one** green (`Ready`) engine to start:
   - **OpenCode (Free):** `curl -fsSL https://opencode.ai/install | bash`
   - **Ollama (100% Offline & Free):** Install from [ollama.com](https://ollama.com) and run `ollama pull qwen2.5-coder`
   - **GitHub Copilot CLI:** `copilot login`
   - **FreeLLMAPI / OpenRouter / Groq:** Run `hxg setup` and paste your URL + API key.
3. **Ask Anything:** Type your question in the **Quick Ask** box on the web dashboard (or run `hxg ask "Explain recursion simply"` in your terminal).

---

## CLI Commands

| Command | What it does |
|---|---|
| `hxg` (or `hxg ui`) | Starts the live web dashboard at `http://127.0.0.1:7878` |
| `hxg ask "your prompt"` | Runs a prompt with automatic model & engine failover (`--task quick\|code\|deep\|review`) |
| `hxg health` | Shows which AI engines are ready right now |
| `hxg status` | Shows active running workers, engine counts, and recent events |
| `hxg watch` | Opens a live auto-refreshing terminal monitor |
| `hxg setup` | 30-second guided setup wizard for API URLs & keys |
| `hxg mcp` | Runs the stdio MCP server (`fleet_health`, `fleet_status`, `fleet_ask`, `fleet_sessions`) |

---

## Connect to AI Coding Tools (MCP)

### Antigravity (`agy`)
```bash
agy mcp add harnessxgate hxg mcp
```

### Claude Desktop / Cursor / Hermes
Add to your MCP config:
```json
{
  "mcpServers": {
    "harnessxgate": {
      "command": "hxg",
      "args": ["mcp"]
    }
  }
}
```

---

## Privacy & Safety
- Runs **100% locally on `127.0.0.1`** — zero cloud telemetry, zero tracking.
- API keys are read from environment variables or `~/.harnessxgate/.env` in memory only and never logged.

## License
MIT — built by **EliLain**.
