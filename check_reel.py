#!/usr/bin/env python3
"""
Validate an MP4 against Instagram Reels API requirements.
Pure stdlib MP4 atom parser -- no ffmpeg needed.

Usage:
    python3 check_reel.py posts/reel.mp4
    python3 check_reel.py https://cdn.jsdelivr.net/gh/OWNER/REPO@main/posts/reel.mp4
"""
import sys, struct, os, urllib.request

# Instagram Reels API limits
MIN_DUR, MAX_DUR = 3, 90          # seconds (5-90 for Reels-tab eligibility)
MAX_SIZE = 100 * 1024 * 1024      # bytes
MIN_W, MIN_H = 540, 960

VIDEO_OK = {"avc1", "h264", "hvc1", "hev1"}   # H.264 / HEVC
AUDIO_OK = {"mp4a"}                            # AAC


def atoms(buf, start, end):
    """Yield (type, payload_start, payload_end) for atoms in [start, end)."""
    p = start
    while p + 8 <= end:
        size = struct.unpack(">I", buf[p:p + 4])[0]
        typ = buf[p + 4:p + 8].decode("latin-1")
        hdr = 8
        if size == 1:                                  # 64-bit extended size
            size = struct.unpack(">Q", buf[p + 8:p + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - p
        if size < hdr:
            break
        yield typ, p + hdr, p + size
        p += size


def find(buf, path, start, end):
    """Walk a slash path like 'moov/trak/mdia'. Returns list of (s,e)."""
    head, _, rest = path.partition("/")
    out = []
    for typ, s, e in atoms(buf, start, end):
        if typ == head:
            out.extend(find(buf, rest, s, e) if rest else [(s, e)])
    return out


def parse(buf):
    info = {"tracks": [], "moov_first": None, "duration": None,
            "major_brand": None}

    top = [(t, s, e) for t, s, e in atoms(buf, 0, len(buf))]
    order = [t for t, _, _ in top]
    if "ftyp" in order and "moov" in order and "mdat" in order:
        info["moov_first"] = order.index("moov") < order.index("mdat")

    for t, s, e in top:
        if t == "ftyp":
            info["major_brand"] = buf[s:s + 4].decode("latin-1", "replace")

    for s, e in find(buf, "moov/mvhd", 0, len(buf)):
        ver = buf[s]
        if ver == 1:
            ts = struct.unpack(">I", buf[s + 20:s + 24])[0]
            du = struct.unpack(">Q", buf[s + 24:s + 32])[0]
        else:
            ts = struct.unpack(">I", buf[s + 12:s + 16])[0]
            du = struct.unpack(">I", buf[s + 16:s + 20])[0]
        if ts:
            info["duration"] = du / ts

    for ts_, te in find(buf, "moov/trak", 0, len(buf)):
        tr = {}
        for s, e in find(buf, "tkhd", ts_, te):
            # width/height are 16.16 fixed point in the LAST 8 bytes of the
            # tkhd payload -- note: end of tkhd (e), not end of trak.
            w = struct.unpack(">I", buf[e - 8:e - 4])[0] >> 16
            h = struct.unpack(">I", buf[e - 4:e])[0] >> 16
            tr["w"], tr["h"] = w, h
        for s, e in find(buf, "mdia/hdlr", ts_, te):
            tr["handler"] = buf[s + 8:s + 12].decode("latin-1", "replace")
        for s, e in find(buf, "mdia/minf/stbl/stsd", ts_, te):
            if e - s >= 16:
                tr["codec"] = buf[s + 12:s + 16].decode("latin-1", "replace")
        for s, e in find(buf, "mdia/mdhd", ts_, te):
            ver = buf[s]
            if ver == 1:
                ts2 = struct.unpack(">I", buf[s + 20:s + 24])[0]
                du2 = struct.unpack(">Q", buf[s + 24:s + 32])[0]
            else:
                ts2 = struct.unpack(">I", buf[s + 12:s + 16])[0]
                du2 = struct.unpack(">I", buf[s + 16:s + 20])[0]
            if ts2:
                tr["dur"] = du2 / ts2
                tr["timescale"] = ts2
        # frame count -> fps
        n = 0
        for s, e in find(buf, "mdia/minf/stbl/stts", ts_, te):
            cnt = struct.unpack(">I", buf[s + 4:s + 8])[0]
            for i in range(cnt):
                o = s + 8 + i * 8
                n += struct.unpack(">I", buf[o:o + 4])[0]
        if n and tr.get("dur"):
            tr["frames"], tr["fps"] = n, n / tr["dur"]
        info["tracks"].append(tr)
    return info


def main(src):
    if src.startswith("http"):
        print(f"Downloading {src} ...")
        req = urllib.request.Request(src, headers={"User-Agent": "check/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            ctype = r.headers.get("Content-Type", "?")
            buf = r.read()
        print(f"  Content-Type: {ctype}")
        if "video" not in ctype:
            print("  NOTE: not served as video/* -- prefer a jsDelivr URL")
    else:
        buf = open(src, "rb").read()

    size = len(buf)
    info = parse(buf)
    vid = next((t for t in info["tracks"] if t.get("handler") == "vide"), None)
    aud = next((t for t in info["tracks"] if t.get("handler") == "soun"), None)
    dur = info["duration"] or (vid or {}).get("dur")

    print("\n===== FILE =====")
    print(f"  Size        : {size/1e6:.2f} MB")
    print(f"  Brand       : {info['major_brand']}")
    print(f"  Duration    : {dur:.2f} s" if dur else "  Duration    : ?")
    print(f"  Tracks      : {len(info['tracks'])}")
    if vid:
        print("\n===== VIDEO =====")
        print(f"  Codec       : {vid.get('codec')}")
        print(f"  Resolution  : {vid.get('w')}x{vid.get('h')}")
        if vid.get("w") and vid.get("h"):
            print(f"  Aspect      : {vid['w']/vid['h']:.4f} "
                  f"(9:16 = 0.5625)")
        if vid.get("fps"):
            print(f"  FPS         : {vid['fps']:.2f} ({vid['frames']} frames)")
    if aud:
        print("\n===== AUDIO =====")
        print(f"  Codec       : {aud.get('codec')}")
        print(f"  Sample rate : {aud.get('timescale')} Hz")
    else:
        print("\n===== AUDIO =====\n  NONE")

    print("\n===== INSTAGRAM REELS CHECK =====")
    checks, fatal = [], []

    def chk(name, ok, detail, hard=True):
        checks.append((ok, name, detail))
        if not ok and hard:
            fatal.append(name)

    chk("Container MP4", info["major_brand"] is not None,
        f"brand={info['major_brand']}")
    chk("Video codec H.264/HEVC", (vid or {}).get("codec") in VIDEO_OK,
        f"got {(vid or {}).get('codec')}")
    chk("Audio codec AAC", aud is not None and aud.get("codec") in AUDIO_OK,
        f"got {(aud or {}).get('codec') if aud else 'no audio track'}")
    chk("Duration in range", bool(dur) and MIN_DUR <= dur <= MAX_DUR,
        f"{dur:.2f}s (API allows {MIN_DUR}-{MAX_DUR}s)" if dur else "unknown")
    chk("File under 100MB", size <= MAX_SIZE, f"{size/1e6:.2f} MB")
    chk("moov atom before mdat (faststart)", info["moov_first"] is True,
        "yes" if info["moov_first"] else "NO -- needs -movflags +faststart")
    if vid and vid.get("w") and vid.get("h"):
        ar = vid["w"] / vid["h"]
        chk("9:16 aspect (Reels tab)", abs(ar - 0.5625) < 0.02,
            f"{vid['w']}x{vid['h']} = {ar:.4f}", hard=False)
        chk("Min 540x960", vid["w"] >= MIN_W and vid["h"] >= MIN_H,
            f"{vid['w']}x{vid['h']}", hard=False)
    if vid and vid.get("fps"):
        chk("FPS 23-60", 23 <= vid["fps"] <= 60,
            f"{vid['fps']:.2f}", hard=False)

    for ok, name, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<32} {detail}")

    print()
    if fatal:
        print(f"RESULT: WILL FAIL -- blocking issues: {', '.join(fatal)}")
        print("\nFix with:")
        print('  ffmpeg -i in.mp4 -c:v libx264 -profile:v high -pix_fmt yuv420p \\\n'
              '    -vf "scale=1080:1920:force_original_aspect_ratio=decrease,'
              'pad=1080:1920:(ow-iw)/2:(oh-ih)/2" \\\n'
              '    -r 30 -c:a aac -b:a 128k -ar 48000 -movflags +faststart out.mp4')
        return 1
    soft = [n for ok, n, _ in checks if not ok]
    if soft:
        print(f"RESULT: WILL PUBLISH, with warnings: {', '.join(soft)}")
    else:
        print("RESULT: PASS -- meets all Instagram Reels API requirements.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
