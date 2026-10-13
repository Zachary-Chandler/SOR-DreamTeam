"""Summarize the structure of the Texas DPS registry export zip without showing record contents.

Usage:
    python inspect_registry.py path/to/registry.zip
    python inspect_registry.py path/to/registry.zip --raw   # also show first line unmasked (header names)

By default the first line of each file is masked: letters -> a/A, digits -> 9,
so you can see delimiters and column layout without any personal data.
"""
import sys
import zipfile
from collections import Counter

DELIMS = [",", "|", "\t", ";"]


def mask(s: str) -> str:
    out = []
    for ch in s:
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("A" if ch.isupper() else "a")
        else:
            out.append(ch)
    return "".join(out)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    raw = "--raw" in sys.argv

    with zipfile.ZipFile(path) as z:
        print(f"Archive: {path}\n")
        for info in z.infolist():
            if info.is_dir():
                continue
            print(f"== {info.filename}  ({info.file_size:,} bytes uncompressed)")
            name = info.filename.lower()
            if not name.endswith((".txt", ".csv", ".tsv", ".dat", ".sql", ".xml", ".xsd")):
                print("   (not a text file I recognize; skipping preview)\n")
                continue
            with z.open(info) as f:
                lines = 0
                first = None
                delim_counts = Counter()
                for i, line in enumerate(f):
                    lines += 1
                    if i == 0:
                        first = line.decode("latin-1").rstrip("\r\n")
                    if i < 50:
                        text = line.decode("latin-1")
                        for d in DELIMS:
                            delim_counts[d] += text.count(d)
            print(f"   lines: {lines:,}")
            if delim_counts:
                d, n = delim_counts.most_common(1)[0]
                if n:
                    print(f"   likely delimiter: {d!r}  (first line has {first.count(d) + 1} fields)")
                else:
                    print("   no common delimiter found (may be fixed-width)")
            if first is not None:
                print(f"   first line length: {len(first)}")
                print(f"   first line (masked): {mask(first)[:300]}")
                if raw:
                    print(f"   first line (raw): {first[:300]}")
            print()


if __name__ == "__main__":
    main()
