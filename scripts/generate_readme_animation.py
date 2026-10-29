"""Render the repository's original animated diagram. Optional dependency: Pillow.

Run: python3 scripts/generate_readme_animation.py
No application dependency, network request or customer data is used.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assets"
WIDTH, HEIGHT, SCALE, FRAMES = 1200, 440, 2, 72


def font(size, bold=False):
    names = [
        "/System/Library/Fonts/Supplemental/Arial" + (" Bold" if bold else "") + ".ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans" + ("-Bold" if bold else "") + ".ttf",
    ]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, round(size * SCALE))
    return ImageFont.load_default(size=round(size * SCALE))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE))
    draw = ImageDraw.Draw(base)
    for y in range(HEIGHT * SCALE):
        fraction = y / (HEIGHT * SCALE)
        draw.line((0, y, WIDTH * SCALE, y), fill=(8, round(26 + fraction * 8), round(31 + fraction * 8)))
    for x in range(0, WIDTH, 32):
        for y in range(0, HEIGHT, 32):
            draw.ellipse((x*SCALE, y*SCALE, x*SCALE+2, y*SCALE+2), fill="#20383c")

    fonts = {key: font(size, bold) for key, size, bold in [
        ("brand", 56, True), ("tag", 27, False), ("body", 14, False),
        ("small", 11, False), ("node", 13, True), ("core", 20, True),
    ]}
    positions = [(726, 99, "OPERATIONS"), (1000, 99, "DOCUMENTS"),
                 (1070, 224, "FORECASTS"), (1000, 350, "SCENARIOS"),
                 (726, 350, "REPORTS"), (655, 224, "INVENTORY")]
    center = (863, 224)
    frames = []
    for frame in range(FRAMES):
        canvas = base.copy()
        d = ImageDraw.Draw(canvas)

        def text(x, y, value, face="body", color="#e7f7f3", anchor=None):
            d.text((x*SCALE, y*SCALE), value, font=fonts[face], fill=color, anchor=anchor)

        def line(points, color, width=1):
            d.line([(x*SCALE, y*SCALE) for x, y in points], fill=color, width=width*SCALE)

        def box(bounds, radius, fill, outline=None):
            d.rounded_rectangle(tuple(round(n*SCALE) for n in bounds), radius=radius*SCALE, fill=fill, outline=outline, width=SCALE)

        def circle(x, y, radius, fill=None, outline=None, width=1):
            d.ellipse(((x-radius)*SCALE, (y-radius)*SCALE, (x+radius)*SCALE, (y+radius)*SCALE), fill=fill, outline=outline, width=width*SCALE)

        text(48, 39, "BUSINESS INTELLIGENCE, CONNECTED", "small", "#8cbbb0")
        text(45, 84, "NEXORA TWIN", "brand")
        text(48, 164, "Understand today.", "tag")
        text(48, 200, "Explore tomorrow.", "tag", "#8de4c8")
        text(48, 254, "Your records. Your evidence. Your next decision.", color="#a1bcb7")
        for index, label in enumerate(["LOCAL AI", "TRACEABLE FACTS", "WHAT-IF LAB"]):
            x = [48, 152, 313][index]
            width = [90, 146, 118][index]
            box((x, 298, x+width, 330), 8, "#123731", "#2a5b4e")
            text(x+width/2, 314, label, "small", "#b2e6d5", "mm")
        text(48, 391, "A LOCAL MVP BUILT AROUND YOUR BUSINESS", "small", "#76988f")

        line([(590, 42), (590, 398)], "#28423f")
        phase = frame / FRAMES
        for radius in [76, 91]:
            circle(*center, radius, outline="#28544a")
        radius = 76 + 20 * phase
        circle(*center, radius, outline="#3a7362")
        for index, (x, y, label) in enumerate(positions):
            line([center, (x, y)], "#365e53")
            progress = (phase * 2 + index / 6) % 1
            px = x + (center[0]-x)*progress
            py = y + (center[1]-y)*progress
            circle(px, py, 6, "#214e40")
            circle(px, py, 2.5, "#a4edce")
            active = (frame // 12) % 6 == index
            box((x-69, y-24, x+69, y+24), 12,
                "#225a48" if active else "#102f2c", "#8cdec0" if active else "#3c695a")
            text(x, y, label, "node", "#d9f7ec" if active else "#a5c9ba", "mm")

        box((798, 169, 928, 279), 22, "#123f34", "#84d9b6")
        # A small vector N mark stays readable even when animation is disabled.
        line([(846, 209), (846, 188), (877, 209), (877, 188)], "#aaf0d5", 4)
        text(863, 236, "YOUR TWIN", "core", anchor="mm")
        text(863, 259, "CONNECTED STATE", "small", "#a2ceba", "mm")
        text(863, 401, "RECORDS   /   INSIGHTS   /   DECISIONS", "small", "#8fb9a5", "mm")

        rendered = canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        if frame == 0:
            rendered.save(OUTPUT / "nexora-hero.png", optimize=True)
            palette = rendered.quantize(colors=128)
        frames.append(rendered.quantize(palette=palette, dither=Image.Dither.NONE))

    frames[0].save(OUTPUT / "nexora-hero.gif", save_all=True, append_images=frames[1:],
                   duration=110, loop=0, optimize=True, disposal=1)
    print(f"Generated {FRAMES} frames, {WIDTH}×{HEIGHT}, with a static reduced-motion alternative.")


if __name__ == "__main__":
    main()
