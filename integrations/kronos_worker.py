"""CPU-only inference using the pinned upstream model and local safetensors checkpoints."""
import json
import math
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path[:0] = [str(BASE / "pyanalytics"), str(BASE / "pydeps"), str(BASE / "upstream" / "Kronos")]

import pandas as pd
import torch
from model import Kronos, KronosPredictor, KronosTokenizer


def main():
    snapshot = json.load(sys.stdin)
    frame = pd.DataFrame(snapshot["bars"])
    observed = pd.to_datetime(frame.pop("time"), utc=True, unit="s")
    step = statistics.median(observed.diff().dropna().dt.total_seconds())
    if step <= 0:
        raise ValueError("Cannot infer an interval from these bars.")
    target = pd.Series([observed.iloc[-1] + pd.to_timedelta(step, unit="s")])
    # Tick counts have no reliable notional conversion in FX. Omit the optional pair for price-only inference.
    frame = frame[["open", "high", "low", "close"]]
    torch.manual_seed(41)
    torch.set_num_threads(2)
    assets = BASE / "models"
    with torch.inference_mode():
        model = Kronos.from_pretrained(str(assets / "Kronos-mini"), local_files_only=True).eval()
        tokenizer = KronosTokenizer.from_pretrained(str(assets / "Kronos-Tokenizer-2k"), local_files_only=True).eval()
        predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=2048)
        forecast = predictor.predict(frame, observed, target, pred_len=1, sample_count=5, verbose=False)
    close = float(forecast["close"].iloc[0])
    if not math.isfinite(close) or close <= 0:
        raise RuntimeError("Model returned an invalid forecast.")
    previous = float(frame["close"].iloc[-1])
    print(f"{snapshot['symbol']} | Kronos-mini | next-interval scenario")
    print(f"Input ends {observed.iloc[-1].isoformat()} | {len(frame)} bars | last close {previous:.8g}")
    print(f"Model close {close:.8g} ({(close / previous - 1):+.2%}) at nominal {target.iloc[0].isoformat()}.")
    print("Five sampled paths averaged, fixed seed. The horizon uses observed median spacing and assumes the market is open.")


if __name__ == "__main__":
    main()
