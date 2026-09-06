"""Measure per-package sizes in a site-packages dir (finds deployment bloat)."""
import os
import sys

sp = sys.argv[1] if len(sys.argv) > 1 else (
    r"C:\Users\basco\AppData\Local\pypoetry\Cache\virtualenvs"
    r"\backend-kjpUGNhm-py3.12\Lib\site-packages"
)

sizes: dict[str, int] = {}
total = 0
for root, dirs, files in os.walk(sp):
    rel = os.path.relpath(root, sp)
    top = rel.split(os.sep)[0].split("-")[0].lower()
    for f in files:
        try:
            s = os.path.getsize(os.path.join(root, f))
        except OSError:
            continue
        sizes[top] = sizes.get(top, 0) + s
        total += s

print(f"TOTAL site-packages: {total / 1e6:.1f} MB")
for name, s in sorted(sizes.items(), key=lambda x: -x[1])[:30]:
    print(f"{s / 1e6:8.1f} MB  {name}")
