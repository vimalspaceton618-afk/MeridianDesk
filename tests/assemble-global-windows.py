"""Animate actual hosted Windows Edge screenshots, with explicit fixture disclosure."""
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont

root=Path(__file__).resolve().parents[1]/"global-preview-output"
meta=json.loads((root/"validation.json").read_text(encoding="utf-8"))
assert meta["market_data_real"] is False and meta["broker_mode"]=="off"
frames,delays=[],[]
fontpath=Path(r"C:\Windows\Fonts\consola.ttf")
font=ImageFont.truetype(str(fontpath),14) if fontpath.is_file() else ImageFont.load_default()
for n,item in enumerate(meta["captures"],1):
    with Image.open(root/"frames"/item["filename"]) as source:
        image=source.convert("RGB")
        image.thumbnail((1120,760),Image.Resampling.LANCZOS)
        w,h=image.size
        frame=Image.new("RGB",(w,h+35),"#09151b")
        frame.paste(image,(0,35))
        draw=ImageDraw.Draw(frame)
        draw.text((14,10),"HOSTED WINDOWS EDGE | SYNTHETIC UI FIXTURES | NOT YOUR PC",font=font,fill="#c6eecf")
        draw.text((w-70,10),f"{n:02d}/{len(meta['captures']):02d}",font=font,fill="#c6eecf")
        frames.append(frame.quantize(colors=128,method=Image.Quantize.FASTOCTREE))
        delays.append(item["duration_ms"])
if not frames:
    raise RuntimeError("No captured Windows UI frames")
output=root/"MeridianDesk-Global-Explorer-Windows-Validation.gif"
frames[0].save(output,save_all=True,append_images=frames[1:],duration=delays,loop=0,optimize=True)
print("GLOBAL_VALIDATION_GIF",output,output.stat().st_size,"bytes",len(frames),"frames")
