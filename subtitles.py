import textwrap

MAX_CHARS = {"9:16": 26, "1:1": 34, "16:9": 44}


def fmt_ts(t):
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_cues(segments, clip_start, clip_end, aspect="9:16"):
    """Subtitle dari segmen transkrip, waktu relatif terhadap awal klip. Maks 2 baris per kemunculan."""
    width = MAX_CHARS.get(aspect, 30)
    cues = []
    for seg in segments:
        s, e = max(seg["start"], clip_start), min(seg["end"], clip_end)
        text = " ".join(seg["text"].split())
        if e <= s or not text:
            continue
        lines = textwrap.wrap(text, width=width) or [text]
        groups = ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
        total = sum(len(g.replace("\n", " ")) for g in groups) or 1
        t = s
        for g in groups:
            share = len(g.replace("\n", " ")) / total
            end = min(e, t + (e - s) * share)
            cues.append((t - clip_start, end - clip_start, g))
            t = end
    return cues


def build_srt(segments, clip_start, clip_end, aspect="9:16"):
    out = []
    for i, (s, e, text) in enumerate(build_cues(segments, clip_start, clip_end, aspect), 1):
        out.append(f"{i}\n{fmt_ts(s)} --> {fmt_ts(e)}\n{text}\n")
    return "\n".join(out)
