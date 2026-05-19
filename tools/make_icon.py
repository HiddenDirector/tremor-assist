"""Generate assets/AppIcon.icns. Run: .venv/bin/python tools/make_icon.py"""

from __future__ import annotations

import math
import os
import subprocess

from AppKit import (
    NSBezierPath,
    NSBitmapImageRep,
    NSColor,
    NSDeviceRGBColorSpace,
    NSGradient,
    NSGraphicsContext,
    NSMakePoint,
    NSMakeRect,
    NSPNGFileType,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONSET = os.path.join(ROOT, "build", "TremorAssist.iconset")
OUT = os.path.join(ROOT, "assets", "AppIcon.icns")


def _color(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255, g / 255, b / 255, a)


def _draw(size: float) -> None:
    inset = size * 0.06
    rect = NSMakeRect(inset, inset, size - 2 * inset, size - 2 * inset)
    radius = (size - 2 * inset) * 0.225
    badge = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)

    # Background gradient.
    grad = NSGradient.alloc().initWithStartingColor_endingColor_(
        _color(38, 198, 168), _color(47, 123, 232)
    )
    grad.drawInBezierPath_angle_(badge, -90.0)

    # Subtle top sheen.
    badge.addClip()
    sheen = NSGradient.alloc().initWithStartingColor_endingColor_(
        _color(255, 255, 255, 0.18), _color(255, 255, 255, 0.0)
    )
    sheen_rect = NSMakeRect(inset, size * 0.55, size - 2 * inset, size * 0.45)
    sheen.drawInRect_angle_(sheen_rect, -90.0)

    mid = size * 0.52
    left = size * 0.18
    right = size * 0.82
    span = right - left

    # tremor line
    jag = NSBezierPath.bezierPath()
    jag.setLineWidth_(max(1.0, size * 0.022))
    jag.setLineCapStyle_(1)
    jag.setLineJoinStyle_(1)
    steps = 60
    for i in range(steps + 1):
        t = i / steps
        x = left + t * span
        wobble = (math.sin(t * 34) * 0.5 + math.sin(t * 61 + 1.3) * 0.5) * (1 - t * 0.5)
        y = mid + wobble * size * 0.16
        pt = NSMakePoint(x, y)
        jag.moveToPoint_(pt) if i == 0 else jag.lineToPoint_(pt)
    _color(255, 255, 255, 0.32).set()
    jag.stroke()

    # steady line
    smooth = NSBezierPath.bezierPath()
    smooth.setLineWidth_(max(1.5, size * 0.05))
    smooth.setLineCapStyle_(1)
    smooth.setLineJoinStyle_(1)
    for i in range(steps + 1):
        t = i / steps
        x = left + t * span
        y = mid + math.sin(t * math.pi * 1.5) * size * 0.10
        pt = NSMakePoint(x, y)
        smooth.moveToPoint_(pt) if i == 0 else smooth.lineToPoint_(pt)
    NSColor.whiteColor().set()
    smooth.stroke()

    # target dot
    dot_r = size * 0.055
    dot = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(right - dot_r, mid + math.sin(1.5 * math.pi) * size * 0.10 - dot_r,
                   dot_r * 2, dot_r * 2)
    )
    NSColor.whiteColor().set()
    dot.fill()


def _render_png(size: int, path: str) -> None:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0
    )
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    _draw(float(size))
    NSGraphicsContext.restoreGraphicsState()
    data = rep.representationUsingType_properties_(NSPNGFileType, {})
    data.writeToFile_atomically_(path, True)


def main() -> None:
    os.makedirs(ICONSET, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    members = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
               (256, 1), (256, 2), (512, 1), (512, 2)]
    for base, scale in members:
        px = base * scale
        name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
        _render_png(px, os.path.join(ICONSET, name))
    subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", OUT], check=True)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
