"""Prepare native Inno resources from the existing Pikachu brand artwork.

Run once with the original transparent brand PNG and ICO as arguments.
Pillow is needed only to prepare assets, not to build or run the installer.
"""
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont


def main():
    root = Path(__file__).resolve().parent / 'assets'
    root.mkdir(exist_ok=True)
    source = Image.open(sys.argv[1]).convert('RGBA')
    shutil.copy2(sys.argv[1], root / 'pikachu-brand.png')
    shutil.copy2(sys.argv[2], root / 'pikachu.ico')
    scale = 3
    canvas = Image.new('RGB', (164 * scale, 314 * scale), '#171219')
    draw = ImageDraw.Draw(canvas)
    pink = '#ff70b6'
    draw.rounded_rectangle((24, 24, 468, 918), radius=48, outline='#4c2a40', width=3)
    font = ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf', 31)
    small = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 18)
    draw.text((57, 81), 'PIKACHU', font=font, fill=pink)
    draw.text((58, 127), 'PHONE WORKBENCH', font=small, fill='#c7a8ba')
    draw.line((58, 171, 194, 171), fill=pink, width=7)
    # Preserve the supplied brand artwork; only resize it for the native bitmap.
    logo = source.copy()
    logo.thumbnail((440, 510), Image.Resampling.LANCZOS)
    canvas.paste(logo, ((canvas.width-logo.width)//2, 274), logo)
    for x, y, size in [(85, 230, 14), (398, 226, 10), (412, 799, 15), (92, 830, 9)]:
        draw.polygon([(x,y-size),(x+4,y-4),(x+size,y),(x+4,y+4),(x,y+size),(x-4,y+4),(x-size,y),(x-4,y-4)],fill=pink)
    draw.text((58, 866), 'CONNECT. CONTROL. CREATE.', font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 13), fill=pink)
    canvas.save(root / 'wizard.bmp')


if __name__ == '__main__':
    main()
