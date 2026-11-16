"""
Cut and encode the recording of the demo, see run.sh.

    python3 docs/demo/encode.py RAW CONTROL OUTPUT [FFMPEG]

Keeps the demo from its beginning to its end, speeds up the waits marked by
demo.py, and writes a small MP4 for LinkedIn and GitHub: H.264, 30 fps, at
most 1280 pixels wide, without sound.
"""

import json
import os
import subprocess
import sys

SPEED = 6
FPS = 30
WIDTH = 1280
# Kept around the demo, in seconds
LEAD = 0.3
TAIL = 0.5


def read(control: str, name: str) -> float:
    with open(os.path.join(control, name)) as f:
        return float(f.read())


def duration(ffmpeg: str, path: str) -> float:
    ffprobe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    output = subprocess.check_output(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            path,
        ]
    )
    return float(output)


def segments(begin: float, end: float, fast: list) -> list:
    """(start, end, speed) covering begin to end, in seconds of the video."""
    result, cursor = [], begin
    for start, stop in sorted(fast):
        start, stop = max(start, cursor), min(stop, end)
        if stop - start < 0.5:
            continue
        if start > cursor:
            result.append((cursor, start, 1))
        result.append((start, stop, SPEED))
        cursor = stop
    if end > cursor:
        result.append((cursor, end, 1))
    return result


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    raw, control, output = sys.argv[1:4]
    ffmpeg = sys.argv[4] if len(sys.argv) == 5 else "ffmpeg"
    with open(os.path.join(control, "marks.json")) as f:
        marks = json.load(f)

    # screencapture takes a moment to start: its first frame comes that late
    started, stopped = read(control, "recording-start"), read(control, "recording-stop")
    length = duration(ffmpeg, raw)
    latency = max(0.0, (stopped - started) - length)
    origin = started + latency

    def at(epoch: float) -> float:
        return min(length, max(0.0, epoch - origin))

    parts = segments(
        at(marks["begin"]) - LEAD,
        at(marks["end"]) + TAIL,
        [(at(a), at(b)) for a, b in marks["fast"]],
    )
    filters = []
    for number, (start, stop, speed) in enumerate(parts):
        filters.append(
            f"[0:v]trim=start={max(0, start):.3f}:end={stop:.3f},"
            f"setpts=(PTS-STARTPTS)/{speed}[v{number}]"
        )
    labels = "".join(f"[v{number}]" for number in range(len(parts)))
    filters.append(
        f"{labels}concat=n={len(parts)}:v=1:a=0,fps={FPS},"
        f"scale='min({WIDTH},iw)':-2:flags=lanczos,format=yuv420p[out]"
    )
    subprocess.check_call(
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-i",
            raw,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "24",
            "-movflags",
            "+faststart",
            "-an",
            output,
        ]
    )
    total = sum((stop - start) / speed for start, stop, speed in parts)
    size = os.path.getsize(output) / 1e6
    print(
        f"{output}: {total:.0f} s, {size:.1f} MB (screencapture latency {latency:.2f} s)"
    )


if __name__ == "__main__":
    main()
