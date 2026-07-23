# Windows NVIDIA Local LLM Setup

This runbook sets up a Windows NVIDIA PC to refresh the portfolio dashboard with local LLM sentiment analysis. Netlify stays a static display/deploy layer; the model runs on your own machine.

You do not need to install Codex on this PC for automation. Codex is useful for development, but the production pieces are:

- Ollama or another local/private LLM runtime
- Git, Python, Node, and the project code
- GitHub self-hosted runner
- GitHub Actions plus Netlify deploy

Recommended first route:

```text
Windows PC + Ollama + GitHub self-hosted runner
```

Later upgrade route:

```text
WSL2/Linux + vLLM or llama.cpp OpenAI-compatible server
```

## 1. Prepare Windows

Recommended:

- Windows 11 or Windows 10+
- Current NVIDIA Game Ready or Studio driver
- RTX 3090 Ti as the main local LLM host; RTX 3060 Ti as a lighter fallback
- 32 GB RAM minimum; 64 GB+ preferred
- 100 GB+ free disk for model files and caches

Check the GPU from PowerShell:

```powershell
nvidia-smi
```

If `nvidia-smi` is missing, install or update the Windows NVIDIA driver first.

## 2. Install Base Tools

Install:

- Git for Windows
- Python 3.11
- Node.js 20 LTS
- GitHub CLI, optional but useful
- Ollama

Check the command-line tools:

```powershell
git --version
python --version
node --version
npm --version
ollama --version
```

Ollama's official Windows installer can be downloaded from `https://ollama.com/download/windows`. Their current PowerShell path is:

```powershell
irm https://ollama.com/install.ps1 | iex
```

Ollama installs in the user profile by default and does not require Administrator for the normal install path.

## 3. Install Models

Start with smaller models before trying larger ones.

3060 Ti first choices:

```powershell
ollama pull qwen3:8b
ollama pull gemma3:4b
```

3090 Ti first choices:

```powershell
ollama pull qwen3:8b
ollama pull qwen3:14b
```

Optional reasoning model for later testing:

```powershell
ollama pull deepseek-r1:14b
```

Smoke test:

```powershell
ollama run qwen3:8b "Use three concise Chinese sentences to explain current market sentiment analysis."
curl http://127.0.0.1:11434/api/tags
```

## 4. Clone And Install The Project

This PC already has the project at:

```text
C:\Users\james\Open_Source\Investing_Portfolio_LR
```

For a fresh machine:

```powershell
mkdir C:\Projects
cd C:\Projects
git clone https://github.com/JamesZCT/Portfolio_Investing_LR.git
cd Portfolio_Investing_LR
```

Install Python dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Install and build the frontend:

```powershell
cd web
npm ci
npm run build
cd ..
```

## 5. Run One Local LLM Snapshot

Set the local LLM environment variables:

```powershell
$env:LLM_SENTIMENT_ENABLED = "true"
$env:LLM_SENTIMENT_PROVIDER = "ollama"
$env:LLM_SENTIMENT_MODEL = "qwen3:8b"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:LLM_SENTIMENT_THINK = "false"
```

Check the LLM endpoint:

```powershell
python scripts/check_local_llm.py --provider ollama --model qwen3:8b
```

Generate snapshots:

```powershell
python scripts/export_web_snapshot.py --config config.yaml --out-dir web/public/data/us --mode real --lookback-days 900
python scripts/export_web_snapshot.py --config example_hk_config.yaml --out-dir web/public/data/hk --mode real --lookback-days 900
Copy-Item web\public\data\us\*.json web\public\data\
```

Confirm the AI layer connected:

```powershell
Get-Content web\public\data\us\sentiment.json | Select-String "llm_generated"
```

If the status is `llm_generated`, the local model contributed the sentiment overlay. If it is `heuristic_default` or `llm_failed_fallback_to_heuristic`, the dashboard still works but used the deterministic sentiment layer.

## 6. Add A GitHub Self-Hosted Runner

In GitHub, open the repository:

```text
Settings -> Actions -> Runners -> New self-hosted runner -> Windows -> x64
```

GitHub will show one-time commands with a registration token. Run exactly those commands on the PC.

Recommended runner directory:

```powershell
mkdir C:\actions-runner
cd C:\actions-runner
```

Use these labels when configuring the runner:

```text
self-hosted
windows
local-llm
nvidia
```

Install the runner as a Windows service so it recovers after reboot. Use an Administrator PowerShell for the service install command that GitHub shows. A logon-triggered Task Scheduler job with `RestartInterval=1 minute` is an acceptable fallback when service installation is unavailable.

The local LLM workflow targets:

```yaml
runs-on: [self-hosted, windows, local-llm]
```

## 7. Run The Automated Refresh

After the runner is online:

1. Open GitHub Actions.
2. Choose `Refresh Web Snapshot Local LLM`.
3. Run it manually with `provider=ollama` and `model=qwen3:14b`.
4. Confirm the workflow commits refreshed `web/public/data/*.json`.
5. Confirm the GitHub Pages deployment succeeds. Netlify runs only when a manual dispatch sets `deploy_to_netlify=true`.

The scheduled workflow can then refresh the hosted dashboard automatically without deploying the model to Netlify or repeatedly consuming OpenAI tokens.

## References

- Ollama Windows download: https://ollama.com/download/windows
- Ollama Windows documentation: https://docs.ollama.com/windows
- GitHub self-hosted runners: https://docs.github.com/en/actions/reference/runners/self-hosted-runners
- GitHub runner labels in workflows: https://docs.github.com/actions/using-jobs/choosing-the-runner-for-a-job
