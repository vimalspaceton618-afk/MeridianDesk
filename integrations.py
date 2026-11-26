"""Run the pinned external research workers in isolated project-local processes."""
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "integrations"
NODE = BASE / "runtime" / "node.exe"
PYTHON = ROOT / "runtime" / "python" / "python.exe"
TA = BASE / "upstream" / "TradingAgents" / "dist" / "cli" / "main.js"
TA_HOME = ROOT / "data" / "tradingagents"
FIELDS = ("open", "high", "low", "close")
PROVIDER_KEYS = ("TAURIC_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
                 "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY")


def statuses():
    """Availability describes installed components and configuration, never live connectivity."""
    checks = [
        ("tradingagents", "TradingAgents", [NODE, TA], "Provider configured; verified on request."),
        ("kronos", "Kronos", [PYTHON, BASE / "kronos_worker.py",
         BASE / "pydeps" / "torch" / "__init__.py", BASE / "pyanalytics" / "pandas" / "__init__.py",
         BASE / "models" / "Kronos-mini" / "model.safetensors",
         BASE / "models" / "Kronos-Tokenizer-2k" / "model.safetensors"],
         "Kronos-mini and tokenizer installed. Runs locally on CPU."),
        ("ruflo", "Ruflo", [NODE, BASE / "ruflo_worker.mjs",
         BASE / "ruflo-dist" / "coordination" / "task-orchestrator.js"],
         "Local swarm with drawdown, volatility, tail-loss and risk review workers."),
    ]
    result = []
    for key, name, files, detail in checks:
        status = "Ready"
        if not all(file.is_file() for file in files):
            status, detail = "Unavailable", "Installation incomplete. Check the integration files on E:."
        elif key == "tradingagents" and not (
                any(os.environ.get(var) for var in PROVIDER_KEYS)
                or os.environ.get("TRADINGAGENTS_BASE_URL") and os.environ.get("TRADINGAGENTS_MODEL")
                or (TA_HOME / "config.json").is_file() or (TA_HOME / "credentials.json").is_file()):
            status, detail = "Setup required", "Set a provider API key or configure a local model in data/tradingagents."
        result.append(dict(id=key, name=name, status=status, detail=detail))
    return result


def _environment():
    if ROOT.drive.upper() != "E:":
        raise RuntimeError("Meridian Desk's integrations require the project on E:.")
    env = os.environ.copy()
    for key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "MERIDIAN_BROKER"):
        env.pop(key, None)
    caches = BASE / "cache"
    profile = caches / "profile"
    paths = {"TEMP": caches / "temp", "TMP": caches / "temp",
             "HOME": profile, "USERPROFILE": profile,
             "APPDATA": profile / "Roaming", "LOCALAPPDATA": profile / "Local",
             "XDG_CACHE_HOME": caches, "HF_HOME": caches / "huggingface",
             "TORCH_HOME": caches / "torch", "TORCHINDUCTOR_CACHE_DIR": caches / "torchinductor",
             "NPM_CONFIG_CACHE": caches / "npm", "TRADINGAGENTS_HOME": TA_HOME}
    for key, path in paths.items():
        path.mkdir(exist_ok=True, parents=True)
        env[key] = str(path)
    env.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", PYTHONDONTWRITEBYTECODE="1",
               TRADINGAGENTS_NO_UPDATE_CHECK="1", TRADINGAGENTS_SYNC="off", NO_COLOR="1",
               PYTHONUTF8="1", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    return env


def _validated(symbol, bars):
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9^#][A-Za-z0-9.:_/#=+^-]{0,45}", symbol):
        raise ValueError("Invalid market symbol.")
    if not isinstance(bars, (list, tuple)) or len(bars) < 32:
        raise ValueError("Collect at least 32 completed OHLC bars before running this analysis.")
    series = []
    for row in bars[-256:]:
        try:
            t = float(row["time"])
            prices = {key: float(row[key]) for key in FIELDS}
            volume = float(row.get("volume", 0) or 0)
            if (not math.isfinite(t) or not 0 < t <= 7258118400 or int(t) != t
                    or any(not math.isfinite(p) or p <= 0 for p in prices.values())
                    or not math.isfinite(volume) or volume < 0
                    or prices["low"] > min(prices["open"], prices["close"])
                    or prices["high"] < max(prices["open"], prices["close"])
                    or series and t <= series[-1]["time"]):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Expected ordered, non-duplicated UTC bars with valid OHLC prices and volume.") from exc
        series.append(dict(time=int(t), **prices, volume=volume))
    return {"symbol": symbol, "bars": series}


def _call(args, env, payload=None, seconds=60, allow_partial=False):
    try:
        proc = subprocess.run([str(a) for a in args], input=payload, text=True, encoding="utf-8",
                              errors="replace", capture_output=True, cwd=BASE, env=env, timeout=seconds,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"The worker exceeded its {seconds}-second time limit.") from exc
    if proc.returncode == 3 and allow_partial and proc.stdout.strip():
        return "Partial research report (configured limit reached)\n\n" + proc.stdout.strip()[:20000]
    if proc.returncode:
        tail = (proc.stderr or proc.stdout or "No diagnostic returned.").strip().splitlines()
        message = " ".join(tail[-3:])[-1200:]
        for key in (*PROVIDER_KEYS, "TRADINGAGENTS_MODEL_API_KEY"):
            value = env.get(key)
            if value:
                message = message.replace(value, "[redacted]")
        message = re.sub(r"(?i)Bearer\s+[\w.\-/+=]+", "Bearer [redacted]", message)
        raise RuntimeError(f"Worker exited {proc.returncode}. {message}")
    if not proc.stdout.strip():
        raise RuntimeError("The worker exited without a report.")
    return proc.stdout.strip()[:20000]


def run_integration(id, symbol, bars):
    """Return a report for the supplied instrument, or raise a user-displayable error."""
    status = next((s for s in statuses() if s["id"] == id), None)
    if not status:
        raise ValueError("Unknown integration.")
    if status["status"] != "Ready":
        raise RuntimeError(status["detail"])
    snapshot = _validated(symbol, bars)
    env = _environment()
    if id == "tradingagents":
        history = snapshot["bars"]
        date = datetime.fromtimestamp(history[-1]["time"], timezone.utc).isoformat()
        first, last = history[0]["close"], history[-1]["close"]
        evidence = {"symbol": symbol, "last_bar_utc": date, "bars": len(history),
                    "first_close": first, "latest_close": last,
                    "low": min(b["low"] for b in history), "high": max(b["high"] for b in history)}
        prompt = ("Give a concise research risk review of this supplied price snapshot. State the as-of time. "
                  "Identify exposure, missing evidence, and one adverse scenario. Distinguish supplied observations "
                  "from outside facts and cite outside sources if used. Do not infer an interval or live execution "
                  "price. Do not place orders. Snapshot " + json.dumps(evidence, allow_nan=False))
        return _call([NODE, TA, "-p", prompt, "--limit", "question.time=60s",
                      "--limit", "question.tokens=30000"], env, seconds=85, allow_partial=True)
    # Neither local worker needs account credentials.
    for key in list(env):
        if key.endswith(("_API_KEY", "_TOKEN")):
            env.pop(key)
    payload = json.dumps(snapshot, allow_nan=False)
    if id == "kronos":
        return _call([PYTHON, "-B", BASE / "kronos_worker.py"], env, payload, seconds=100)
    return _call([NODE, BASE / "ruflo_worker.mjs"], env, payload, seconds=20)
