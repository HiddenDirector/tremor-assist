"""Throughput benchmark: pure-Python vs native C One Euro Filter.

Run after building the native libs:

    ./native/build.sh
    .venv/bin/python native/bench.py
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tremor_assist import native
from tremor_assist.one_euro import OneEuroFilter2D

N = 1_000_000


def signal(n):
    pts = []
    for i in range(n):
        t = i / 120.0
        x = 100.0 + 30.0 * math.sin(2 * math.pi * 1.5 * t) + 4.0 * math.sin(2 * math.pi * 9 * t)
        y = 80.0 + 3.0 * math.cos(2 * math.pi * 8 * t)
        pts.append((x, y, t))
    return pts


def run(filt, pts):
    start = time.perf_counter()
    for x, y, t in pts:
        filt.filter(x, y, t)
    return time.perf_counter() - start


def main():
    pts = signal(N)

    py = run(OneEuroFilter2D(1.0, 0.02, 1.0), pts)
    print(f"python : {py:7.3f}s  {N / py / 1e6:6.2f} M events/s")

    if native.CORE_AVAILABLE:
        c = run(native.NativeOneEuroFilter2D(1.0, 0.02, 1.0), pts)
        print(f"native : {c:7.3f}s  {N / c / 1e6:6.2f} M events/s")
        print(f"speedup: {py / c:5.2f}x")
    else:
        print("native core not built - run ./native/build.sh")


if __name__ == "__main__":
    main()
