"""Deteksi highlight berbasis TRANSKRIP saja (heuristik). Tidak menganalisis visual video."""
import re

HOOKS = {
    "rahasia", "ternyata", "jangan", "kesalahan", "bayangkan", "faktanya", "masalahnya", "kenapa",
    "mengapa", "bagaimana", "penting", "gila", "luar", "pertama", "alasan", "tips", "cara", "terbesar",
    "secret", "truth", "mistake", "never", "always", "imagine", "why", "how", "important", "crazy",
    "amazing", "biggest", "reason", "nobody", "everyone", "actually", "best", "stop", "wrong",
}
EMPHASIS = HOOKS | {"harus", "wajib", "pasti", "selalu", "tidak", "must", "need", "key", "problem", "solution"}
CONTINUATION = {
    "dan", "tapi", "tetapi", "karena", "sehingga", "atau", "lalu", "terus", "makanya",
    "and", "but", "so", "or", "because", "then", "which", "that",
}
QUESTION_START = {"apa", "kenapa", "mengapa", "bagaimana", "siapa", "kapan", "dimana", "what", "why", "how", "who", "when", "where", "do", "did", "is", "are", "can"}


def _words(text):
    return re.findall(r"\w+", text.lower())


def _complete(text):
    return bool(re.search(r"[.!?…][\"'”’)\]]*\s*$", text.strip()))


def _gap_after(segs, j):
    return segs[j + 1]["start"] - segs[j]["end"] if j + 1 < len(segs) else 999.0


def _windows(segs, min_d, max_d):
    out = set()
    for i in range(len(segs)):
        start = segs[i]["start"]
        ends = []
        for j in range(i, len(segs)):
            dur = segs[j]["end"] - start
            if dur > max_d:
                break
            if dur >= min_d and (_complete(segs[j]["text"]) or _gap_after(segs, j) >= 1.5):
                ends.append(j)
        if ends:
            out.add((i, ends[0]))
            out.add((i, ends[-1]))
    if not out:  # tidak ada akhir kalimat yang cocok: potong di batas segmen terdekat
        for i in range(len(segs)):
            best = None
            for j in range(i, len(segs)):
                dur = segs[j]["end"] - segs[i]["start"]
                if dur > max_d:
                    break
                if dur >= min_d:
                    best = j
            if best is not None:
                out.add((i, best))
    return sorted(out)


def _score(segs, i, j, min_d, max_d):
    first = segs[i]["text"].strip()
    fw = _words(first)
    text = " ".join(s["text"].strip() for s in segs[i:j + 1])
    words = _words(text)
    dur = segs[j]["end"] - segs[i]["start"]
    score, why = 0.0, []

    if "?" in first or (fw and fw[0] in QUESTION_START):
        score += 2; why.append("dibuka dengan pertanyaan")
    if any(w in HOOKS for w in fw[:12]):
        score += 2; why.append("kalimat pembuka memuat kata penarik perhatian")
    if re.search(r"\d", first):
        score += 1; why.append("pembuka memuat angka/fakta")
    q = text.count("?") - first.count("?")
    if q > 0:
        score += min(q, 3) * 0.7; why.append(f"memuat {q} pertanyaan lanjutan")
    if words:
        dens = sum(w in EMPHASIS for w in words) / len(words) * 100
        if dens >= 2:
            score += min(dens / 2, 3); why.append("banyak pernyataan penting/penekanan")
    ex = text.count("!")
    if ex:
        score += min(ex, 3) * 0.5; why.append("ada kalimat berintonasi tegas (!)")

    gap_before = segs[i]["start"] - segs[i - 1]["end"] if i > 0 else 999.0
    if gap_before >= 1.5:
        score += 1.5; why.append("dimulai setelah jeda (kemungkinan pergantian topik)")
    if i > 0:
        a, b = {w for w in _words(segs[i - 1]["text"]) if len(w) > 3}, {w for w in fw if len(w) > 3}
        if a and b and len(a & b) / len(a | b) < 0.1:
            score += 1; why.append("kosakata berbeda dari segmen sebelumnya")

    if fw and fw[0] not in CONTINUATION:
        score += 1.5; why.append("kalimat awal berdiri sendiri")
    else:
        score -= 2
    if _complete(segs[j]["text"]):
        score += 1.5; why.append("berakhir di akhir kalimat")
    else:
        score -= 1.5

    wps = len(words) / dur if dur else 0
    if 1.5 <= wps <= 4.5:
        score += 1; why.append("kepadatan bicara baik")
    elif wps < 0.8:
        score -= 2
    mid = (min_d + max_d) / 2
    score += max(0.0, 1 - abs(dur - mid) / max(mid, 1))
    return round(score, 2), "; ".join(why) or "kandidat umum berdasarkan transkrip"


def adaptive_params(duration):
    return {"clip_count": max(3, min(8, round(duration / 300))), "min_duration": 20, "max_duration": 60}


def find_highlights(segments, video_duration, clip_count, min_d, max_d):
    segs = [s for s in segments if s["text"].strip()]
    if not segs:
        return []
    if video_duration <= min_d:
        text = " ".join(s["text"].strip() for s in segs)
        return [{"start": 0.0, "end": round(video_duration, 2), "score": 0.0,
                 "reason": "video lebih pendek dari durasi minimum; seluruh video dipakai", "text": text[:240]}]
    scored = []
    for i, j in _windows(segs, min_d, max_d):
        sc, why = _score(segs, i, j, min_d, max_d)
        scored.append((sc, i, j, why))
    scored.sort(key=lambda x: -x[0])
    chosen = []
    for sc, i, j, why in scored:
        s, e = segs[i]["start"], segs[j]["end"]
        if any(s < c["end"] and e > c["start"] for c in chosen):
            continue
        text = " ".join(x["text"].strip() for x in segs[i:j + 1])
        chosen.append({"start": round(s, 2), "end": round(e, 2), "score": sc,
                       "reason": "Berdasarkan transkrip: " + why, "text": text[:240]})
        if len(chosen) >= clip_count:
            break
    return sorted(chosen, key=lambda c: c["start"])
