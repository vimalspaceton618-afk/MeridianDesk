"""Create an animated validation GIF from real Windows Edge screenshot frames.

The source images come from the hosted Windows runner's Playwright session.
The small header is a disclosure, not a reconstruction of the UI.
"""
from PIL import Image, ImageDraw, ImageFont
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "preview-output"
meta = json.loads((root / "validation.json").read_text(encoding="utf-8"))
assert meta["simulated"] is True and meta["broker_mode"] == "off"
frames = []
durations = []
font_path = Path(r"C:\Windows\Fonts\segoeui.ttf")
font = ImageFont.truetype(str(font_path), 14) if font_path.exists() else ImageFont.load_default()
for idx, entry in enumerate(meta["captures"], start=1):
    source = root / "frames" / entry["filename"]
    assert source.is_file(), source
    with Image.open(source) as frame:
        rendered = frame.convert("RGB")
        rendered.thumbnail((1120, 720), Image.Resampling.LANCZOS)
        w, h = rendered.size
        canvas = Image.new("RGB", (w, h + 34), "#0d1928")
        canvas.paste(rendered, (0, 34))
        draw = ImageDraw.Draw(canvas)
        draw.text((14, 9), "HOSTED WINDOWS / MICROSOFT EDGE  |  DEMO SIMULATION  |  NOT USER'S PC", font=font, fill="#b6daef")
        draw.text((w - 72, 9), f"{idx:02d}/{len(meta['captures']):02d}", font=font, fill="#b6daef")
        frames.append(canvas.quantize(colors=128, method=Image.Quantize.FASTOCTREE))
        durations.append(entry["duration_ms"])
assert frames
gif = root / "MeridianDesk-Windows-Edge-Functional-Validation.gif"
frames[0].save(gif, save_all=True, append_images=frames[1:],
               duration=durations, loop=0, optimize=True)
print("VALIDATION_GIF", str(gif), gif.stat().st_size, "bytes", len(frames), "frames")
