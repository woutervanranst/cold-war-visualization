#!/usr/bin/env python3
"""Validate per-chapter extracts and build data/coldwar.json.

Usage:
  python3 tools/build_data.py --check work/extract/ch05.json [...]   validate extract files
  python3 tools/build_data.py                                        build data/coldwar.json

Inputs: tools/roster.json (committed), work/chapters.json, work/index.json,
work/text/*.txt, work/extract/chNN.json, work/timelines.json (all from the epub; gitignored).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
KINDS = {"summit", "war", "crisis", "treaty", "revolution", "split", "independence", "collapse",
         "coup", "intervention", "speech", "policy", "uprising", "election", "other"}
DATE_RE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")
NOTE_MAX_WORDS = 35
NGRAM = 8
MAIN_CAST = {"countries": 20, "leaders": 22}   # how many of each make the "main cast"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def words(text):
    text = re.sub(r"\[p\.\d+\]", " ", text.lower())
    return re.findall(r"[a-z0-9]+(?:['’][a-z]+)?", text)


_book_ngrams = None


def book_ngrams():
    """Set of all 8-word sequences in the book, for the copy check."""
    global _book_ngrams
    if _book_ngrams is None:
        ws = []
        for f in sorted((WORK / "text").glob("ch*.txt")):
            ws += words(f.read_text(encoding="utf-8"))
        _book_ngrams = {tuple(ws[i:i + NGRAM]) for i in range(len(ws) - NGRAM + 1)}
    return _book_ngrams


def copied_run(note):
    w = words(note)
    grams = book_ngrams()
    for i in range(len(w) - NGRAM + 1):
        if tuple(w[i:i + NGRAM]) in grams:
            return " ".join(w[i:i + NGRAM])
    return None


class Ctx:
    def __init__(self):
        self.roster = load(ROOT / "tools" / "roster.json")
        self.chapters = {c["n"]: c for c in load(WORK / "chapters.json")}
        self.countries = {c["id"] for c in self.roster["countries"]}
        self.leaders = {l["id"] for l in self.roster["leaders"]}
        self.bands = {b["id"] for b in self.roster["bands"]}

    def page_ok(self, ch, p):
        c = self.chapters.get(ch)
        return c is not None and isinstance(p, int) and c["pages"][0] <= p <= c["pages"][1]


def check_note(where, note, errs):
    if not isinstance(note, str) or not note.strip():
        errs.append(f"{where}: missing note")
        return
    n = len(note.split())
    if n > NOTE_MAX_WORDS:
        errs.append(f"{where}: note has {n} words (max {NOTE_MAX_WORDS})")
    run = copied_run(note)
    if run:
        errs.append(f"{where}: note copies book text: '{run}'")


def check_extract(ctx, path):
    errs = []
    d = load(path)
    ch = d.get("chapter")
    if ch not in ctx.chapters:
        return [f"{path}: bad chapter {ch!r}"]
    for key in ("alignment_evidence", "leader_evidence", "events", "candidates"):
        if not isinstance(d.get(key), list):
            errs.append(f"{path}: '{key}' must be a list")
    if errs:
        return errs

    for i, a in enumerate(d["alignment_evidence"]):
        w = f"alignment[{i}] {a.get('country')}"
        if a.get("country") not in ctx.countries:
            errs.append(f"{w}: unknown country")
        if a.get("band") not in ctx.bands:
            errs.append(f"{w}: unknown band {a.get('band')!r}")
        if not DATE_RE.match(str(a.get("date"))):
            errs.append(f"{w}: bad date {a.get('date')!r}")
        if not ctx.page_ok(ch, a.get("page")):
            errs.append(f"{w}: page {a.get('page')!r} outside chapter {ch}")
        check_note(w, a.get("note"), errs)

    for i, l in enumerate(d["leader_evidence"]):
        w = f"leader[{i}] {l.get('leader')}"
        if l.get("leader") not in ctx.leaders:
            errs.append(f"{w}: unknown leader")
        for k in ("start", "end"):
            if l.get(k) is not None and not DATE_RE.match(str(l[k])):
                errs.append(f"{w}: bad {k} {l[k]!r}")
        if not ctx.page_ok(ch, l.get("page")):
            errs.append(f"{w}: page {l.get('page')!r} outside chapter {ch}")

    ids = set()
    for i, e in enumerate(d["events"]):
        w = f"event[{i}] {e.get('id')}"
        if not re.match(r"^[a-z0-9-]+$", str(e.get("id"))):
            errs.append(f"{w}: id must be kebab-case")
        if e.get("id") in ids:
            errs.append(f"{w}: duplicate id")
        ids.add(e.get("id"))
        if not DATE_RE.match(str(e.get("date"))):
            errs.append(f"{w}: bad date {e.get('date')!r}")
        if e.get("kind") not in KINDS:
            errs.append(f"{w}: kind {e.get('kind')!r} not in {sorted(KINDS)}")
        if e.get("rank") not in (1, 2, 3):
            errs.append(f"{w}: rank must be 1, 2 or 3")
        if not isinstance(e.get("title"), str) or not (1 <= len(e["title"].split()) <= 8):
            errs.append(f"{w}: title must be 1-8 words")
        bad = [c for c in e.get("countries", []) if c not in ctx.countries]
        bad += [l for l in e.get("leaders", []) if l not in ctx.leaders]
        if bad:
            errs.append(f"{w}: unknown participants {bad}")
        if not e.get("countries") and not e.get("leaders"):
            errs.append(f"{w}: no participants")
        refs = e.get("refs") or []
        if not refs:
            errs.append(f"{w}: no refs")
        for r in refs:
            if r.get("ch") != ch or not ctx.page_ok(ch, r.get("p")):
                errs.append(f"{w}: ref {r} not a page in chapter {ch}")
        check_note(w, e.get("note"), errs)
    return errs


def month_key(date):
    """'1962-10' -> 1962*12+9; '1962' -> (1962*12+5, year-only)."""
    y, _, m = date.partition("-")
    return int(y) * 12 + (int(m) - 1 if m else 5), not m


def load_extracts(ctx):
    exts = []
    for p in sorted((WORK / "extract").glob("ch*.json")):
        errs = check_extract(ctx, p)
        if errs:
            sys.exit(f"{p} fails --check ({len(errs)} problems); fix it first")
        exts.append(load(p))
    return exts


def title_words(title):
    return {w for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 3}


def merge_events(exts, aliases=None):
    """Merge the same event reported by several chapters (same id, or same month +
    same kind + mostly the same participants, or same month + similar title)."""
    aliases = aliases or {}
    merged = []
    for d in exts:
        for e in d["events"]:
            e = {**e, "id": aliases.get(e["id"], e["id"]), "countries": list(dict.fromkeys(e.get("countries", []))),
                 "leaders": list(dict.fromkeys(e.get("leaders", [])))}
            hit = None
            for m in merged:
                if m["id"] == e["id"]:
                    hit = m
                    break
                mk, mq = month_key(m["date"])
                ek, eq = month_key(e["date"])
                close = abs(mk - ek) <= (6 if (mq or eq) else 1)
                a = set(m["countries"]) | set(m["leaders"])
                b = set(e["countries"]) | set(e["leaders"])
                if close and m["kind"] == e["kind"] and a and b and len(a & b) / len(a | b) >= 0.6:
                    hit = m
                    break
                same_month = mk == ek and mq == eq
                shared = title_words(m["title"]) & title_words(e["title"])
                if same_month and len(shared) >= 2 and a & b:
                    hit = m
                    break
            if hit is None:
                merged.append(e)
                continue
            better = e["rank"] < hit["rank"]
            if better:
                hit.update(title=e["title"], note=e["note"], rank=e["rank"])
            if month_key(hit["date"])[1] and not month_key(e["date"])[1]:
                hit["date"] = e["date"]
            hit["countries"] = list(dict.fromkeys(hit["countries"] + e["countries"]))
            hit["leaders"] = list(dict.fromkeys(hit["leaders"] + e["leaders"]))
            hit["refs"] = hit["refs"] + [r for r in e["refs"] if r not in hit["refs"]]
    for m in merged:
        m["refs"].sort(key=lambda r: (r["ch"], r["p"]))
    merged.sort(key=lambda m: (month_key(m["date"])[0], m["id"]))
    seen = set()
    for m in merged:   # ids must stay unique after merging
        base, n = m["id"], 2
        while m["id"] in seen:
            m["id"] = f"{base}-{n}"
            n += 1
        seen.add(m["id"])
    return merged


def draft_timelines(ctx, exts):
    """Sort alignment evidence per country and collapse repeats; a starting point
    for the hand-curated tools/timelines.json."""
    ev = {c: [] for c in ctx.countries}
    for d in exts:
        for a in d["alignment_evidence"]:
            ev[a["country"]].append({**a, "ch": d["chapter"]})
    out = {}
    for cid, items in ev.items():
        items.sort(key=lambda a: (month_key(a["date"])[0], a["ch"]))
        segs = []
        for a in items:
            if segs and segs[-1]["band"] == a["band"]:
                continue
            segs.append({"from": a["date"], "band": a["band"], "note": a["note"],
                         "ref": {"ch": a["ch"], "p": a["page"]}})
        out[cid] = {"segments": segs, "evidence": [
            f"{a['date']:>7} {a['band']:<15} ch{a['ch']:02d} p{a['page']}: {a['note']}" for a in items]}
    return out


def index_chapters(ctx):
    idx = load(WORK / "index.json")
    by_term = {}
    for e in idx:
        by_term.setdefault(e["term"], set()).update(r["ch"] for r in e["refs"])
    return by_term


def index_counts():
    counts = {}
    for e in load(WORK / "index.json"):
        counts[e["term"]] = counts.get(e["term"], 0) + len(e["refs"])
    return counts


def mark_main_cast(roster, countries, leaders, events):
    """Flag the entities the book leans on most: index references plus events
    they take part in (rank 1 counts 3, rank 2 counts 2, rank 3 counts 1)."""
    refs = index_counts()
    terms = {c["id"]: c.get("terms", []) for c in roster["countries"]}
    terms.update({l["id"]: [l["term"]] for l in roster["leaders"]})
    for key, items in (("countries", countries), ("leaders", leaders)):
        score = {x["id"]: sum(refs.get(t, 0) for t in terms[x["id"]])
                 + sum(4 - e["rank"] for e in events if x["id"] in e[key]) for x in items}
        top = sorted(items, key=lambda x: -score[x["id"]])[:MAIN_CAST[key]]
        for x in top:
            x["main"] = True
        print(f"main cast {key}: " + ", ".join(x["id"] for x in top))


def build(ctx):
    exts = load_extracts(ctx)
    tl_path = ROOT / "tools" / "timelines.json"
    if not tl_path.exists():
        draft = draft_timelines(ctx, exts)
        (WORK / "timelines.draft.json").write_text(json.dumps(draft, indent=1, ensure_ascii=False), encoding="utf-8")
        sys.exit(f"no tools/timelines.json yet; wrote {WORK / 'timelines.draft.json'} to curate from")
    tl = load(tl_path)
    roster = ctx.roster
    events = merge_events(exts, tl.get("eventAliases"))
    by_term = index_chapters(ctx)
    errs, warns = [], []

    # hand corrections from the fact-check pass
    by_id = {e["id"]: e for e in events}
    for eid, fx in tl.get("eventFixes", {}).items():
        e = by_id.get(eid)
        if e is None:
            errs.append(f"eventFixes: unknown event {eid}")
            continue
        if fx.get("delete"):
            events.remove(e)
            continue
        drop = fx.get("dropRefs", [])
        e["refs"] = [r for r in e["refs"] if r not in drop]
        e.update({k: v for k, v in fx.items() if k not in ("dropRefs", "delete")})
        if "note" in fx:
            check_note(f"eventFixes {eid}", fx["note"], errs)
        bad = [c for c in e["countries"] if c not in ctx.countries] + [l for l in e["leaders"] if l not in ctx.leaders]
        if bad:
            errs.append(f"eventFixes {eid}: unknown participants {bad}")

    def ev_chapters(eid_key, ent_id):
        return {r["ch"] for e in events if ent_id in e[eid_key] for r in e["refs"]}

    countries = []
    for c in roster["countries"]:
        t = tl["countries"].get(c["id"])
        if not t or not t.get("segments"):
            errs.append(f"country {c['id']}: no curated timeline")
            continue
        segs = t["segments"]
        prev = None
        for s in segs:
            w = f"timeline {c['id']} {s.get('from')}"
            if not DATE_RE.match(str(s.get("from"))):
                errs.append(f"{w}: bad date")
            if s.get("band") not in ctx.bands:
                errs.append(f"{w}: bad band {s.get('band')!r}")
            if prev and month_key(s["from"])[0] <= month_key(prev["from"])[0]:
                errs.append(f"{w}: segments out of order")
            if prev and prev["band"] == s["band"]:
                errs.append(f"{w}: repeats band {s['band']}")
            ref = s.get("ref")
            if ref and not ctx.page_ok(ref.get("ch"), ref.get("p")):
                errs.append(f"{w}: bad ref {ref}")
            check_note(w, s.get("note"), errs)
            prev = s
        chs = set()
        for term in c.get("terms", []):
            chs |= by_term.get(term, set())
        chs |= ev_chapters("countries", c["id"])
        out = {"id": c["id"], "name": c["name"], "short": c.get("short", c["name"]), "region": c["region"], "segments": segs,
               "chapters": sorted(chs)}
        for k in ("parent", "mergeInto"):
            if c.get(k):
                out[k] = c[k]
        if t.get("end"):
            out["end"] = t["end"]
        countries.append(out)

    leaders = []
    for l in roster["leaders"]:
        t = tl["leaders"].get(l["id"])
        if not t or not t.get("terms"):
            errs.append(f"leader {l['id']}: no curated terms")
            continue
        for a, b in t["terms"]:
            if not DATE_RE.match(a) or (b and not DATE_RE.match(b)) or (b and month_key(b)[0] < month_key(a)[0]):
                errs.append(f"leader {l['id']}: bad term {a}–{b}")
        chs = by_term.get(l["term"], set()) | ev_chapters("leaders", l["id"])
        n_ev = sum(l["id"] in e["leaders"] for e in events)
        if not n_ev:
            warns.append(f"leader {l['id']} has no events")
        leaders.append({"id": l["id"], "name": l["name"], "short": l.get("short", l["name"].split()[-1]),
                        "country": l["country"], "seat": l["seat"],
                        "role": t.get("role", ""), "terms": [{"start": a, "end": b} for a, b in t["terms"]],
                        "dateSource": t.get("dateSource", "general"), "chapters": sorted(chs)})

    # simultaneous country lines, and how far lines travel for this band order
    band_order = [b["id"] for b in roster["bands"]]
    for year in range(1890, 2018, 5):
        n = sum(1 for c in countries if month_key(c["segments"][0]["from"])[0] <= year * 12
                and (not c.get("end") or month_key(c["end"])[0] > year * 12))
        if n > 35:
            warns.append(f"{n} country lines at once in {year}")

    def travel(order):
        pos = {b: i for i, b in enumerate(order)}
        return sum(abs(pos[s1["band"]] - pos[s0["band"]]) for c in countries
                   for s0, s1 in zip(c["segments"], c["segments"][1:]))
    score = travel(band_order)
    better = []
    for i in range(len(band_order) - 1):
        o = band_order[:]
        o[i], o[i + 1] = o[i + 1], o[i]
        if travel(o) < score:
            better.append(f"swap {o[i + 1]}<->{o[i]}: {travel(o)} < {score}")

    mark_main_cast(roster, countries, leaders, events)
    chapters = []
    for c in sorted(ctx.chapters.values(), key=lambda c: c["n"]):
        ts = sorted(month_key(e["date"])[0] / 12 for e in events if any(r["ch"] == c["n"] for r in e["refs"]))
        span = None
        if ts:
            lo, hi = ts[int(len(ts) * 0.1)], ts[min(len(ts) - 1, int(len(ts) * 0.9))]
            span = [round(max(1890, lo), 2), round(min(2017, hi + 1 / 12), 2)]
        chapters.append({**c, "span": span})

    if errs:
        print("\n".join("ERROR " + e for e in errs))
        sys.exit(f"{len(errs)} errors; data/coldwar.json not written")
    data = {
        "meta": {"title": "The Cold War: A World History", "author": "Odd Arne Westad",
                 "publisher": "Basic Books", "year": 2017},
        "chapters": chapters,
        "bands": [{"id": b["id"], "labels": b["labels"]} for b in roster["bands"]],
        "regions": roster["regions"],
        "countries": countries, "leaders": leaders, "events": events,
    }
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "coldwar.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"data/coldwar.json: {len(countries)} countries, {len(leaders)} leaders, {len(events)} events "
          f"(from {sum(len(d['events']) for d in exts)} extracted)")
    print(f"band order travel score {score}; " + ("; ".join(better) if better else "no adjacent swap improves it"))
    print("events per chapter: " + " ".join(
        f"{c['n']}:{sum(any(r['ch'] == c['n'] for r in e['refs']) for e in events)}" for c in chapters))
    dec = {}
    for e in events:
        dec[int(e["date"][:4]) // 10 * 10] = dec.get(int(e["date"][:4]) // 10 * 10, 0) + 1
    print("events per decade: " + " ".join(f"{k}s:{v}" for k, v in sorted(dec.items())))
    for w in warns:
        print("WARN", w)


def main(argv):
    ctx = Ctx()
    if argv[:1] == ["--draft"]:
        draft = draft_timelines(ctx, load_extracts(ctx))
        (WORK / "timelines.draft.json").write_text(json.dumps(draft, indent=1, ensure_ascii=False), encoding="utf-8")
        for cid, d in draft.items():
            print(f"\n## {cid}: " + " | ".join(f"{s['from']} {s['band']}" for s in d["segments"]))
            for line in d["evidence"]:
                print("   ", line)
        return
    if argv[:1] == ["--check"]:
        bad = 0
        for p in argv[1:]:
            errs = check_extract(ctx, p)
            d = load(p)
            print(f"{p}: {len(d.get('events', []))} events, "
                  f"{len(d.get('alignment_evidence', []))} alignment, "
                  f"{len(d.get('leader_evidence', []))} leader evidence -> "
                  f"{'OK' if not errs else f'{len(errs)} problems'}")
            for e in errs:
                print("  -", e)
            bad += bool(errs)
        sys.exit(1 if bad else 0)
    build(ctx)


if __name__ == "__main__":
    main(sys.argv[1:])
