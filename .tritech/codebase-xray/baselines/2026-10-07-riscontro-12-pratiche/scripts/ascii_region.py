"""Print a screenshot region as an intensity grid, one character per source pixel.

Usage: python -I ascii_region.py <image> <x0> <y0> <x1> <y1>
For the ~7px table font, where 6/8/9 differ by one or two pixels and upscaling only blurs them.
Reading key (rows counted from the top of the digit): a 6 has its bar on row 3 joined to the
left stroke; an 8 has its waist on row 4, centred, with both side strokes above and below;
a 9 has its bar on row 5 joined to the right stroke.
"""
import sys

from PIL import Image

path = sys.argv[1]
x0, y0, x1, y1 = map(int, sys.argv[2:6])
img = Image.open(path).convert("L").crop((x0, y0, x1, y1))
px = img.load()
ramp = " .:-=+*#%@"
print(f"{path} box=({x0},{y0},{x1},{y1})")
for y in range(img.height):
    print(f"{y0 + y:5d} " + "".join(ramp[min(9, (255 - px[x, y]) * 10 // 256)] for x in range(img.width)))
