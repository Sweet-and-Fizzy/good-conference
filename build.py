#!/usr/bin/env python3
"""Build the GOOD conference archive site from data/ into site/.

    python3 build.py

Inputs, per year, in data/:
  <year>.json                 hand-written: dates, venue, overview, sponsors, resources
  <year>-schedule.json        pretalx schedule export (schedule.json), verbatim
  <year>-recordings.json      optional: [{"vimeo_id": ..., "title": ...}] matched to talks by title

Output: site/ (static HTML + copied assets). No dependencies beyond the standard library.
"""
import difflib
import html
import json
import os
import re
import shutil
from collections import OrderedDict
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "site")
YEARS = sorted(f[:-5] for f in os.listdir(DATA) if re.fullmatch(r"\d{4}\.json", f))

E = html.escape


# ---------- tiny markdown (pretalx abstracts are mostly plain text) ----------

def md(text):
    if not text:
        return ""
    text = text.replace("\r\n", "\n").strip()
    text = E(text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"(?<![\w/\"=>])(https?://[^\s<)\"]+)", r'<a href="\1">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.split("\n")
        if all(re.match(r"\s*[-*] ", l) for l in lines):
            out.append("<ul>" + "".join("<li>%s</li>" % re.sub(r"^\s*[-*] ", "", l) for l in lines) + "</ul>")
        else:
            out.append("<p>%s</p>" % "<br>".join(lines))
    return "\n".join(out)


def norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


# ---------- data ----------

def load_year(year):
    meta = json.load(open(os.path.join(DATA, f"{year}.json")))
    conf = json.load(open(os.path.join(DATA, meta["program_source"])))["schedule"]["conference"]
    talks = []
    for day in conf["days"]:
        for room, items in day["rooms"].items():
            for t in items:
                t = dict(t)
                t["room"] = room
                t["day"] = day["date"]
                talks.append(t)
    # de-duplicate (pretalx repeats a talk that spans rooms)
    seen, uniq = set(), []
    for t in talks:
        if t["code"] in seen:
            continue
        seen.add(t["code"])
        uniq.append(t)
    merged = OrderedDict()
    for t in sorted(uniq, key=lambda t: (t["day"], t["start"], t["room"])):
        key = (t["day"], t["start"], norm(t["title"]))
        if key in merged:
            m = merged[key]
            m["rooms"].append(t["room"])
            m["codes"].append(t["code"])
            for p in t["persons"]:
                if p["code"] not in {q["code"] for q in m["persons"]}:
                    m["persons"].append(p)
        else:
            t["rooms"] = [t["room"]]
            t["codes"] = [t["code"]]
            merged[key] = t
    talks = list(merged.values())

    recordings = {}
    if meta.get("recordings_source"):
        clips = json.load(open(os.path.join(DATA, meta["recordings_source"])))
        titles = {norm(t["title"]): t["code"] for t in talks}
        for c in clips:
            ct = norm(re.sub(r"\s*-\s*GOOD Conference \d{4}\s*$", "", c["title"]))
            best = max(titles, key=lambda k: difflib.SequenceMatcher(None, ct, k).ratio())
            if difflib.SequenceMatcher(None, ct, best).ratio() >= 0.75:
                recordings[titles[best]] = c["vimeo_id"]

    people = OrderedDict()
    for t in talks:
        for p in t["persons"]:
            person = people.setdefault(p["code"], {"code": p["code"], "name": p["public_name"], "bio": p.get("biography") or "", "talks": []})
            if t["code"] not in person["talks"]:
                person["talks"].append(t["code"])
            av = os.path.join(ROOT, "assets", "avatars", year, p["code"] + ".webp")
            for ext in (".webp", ".jpg", ".png", ".jpeg"):
                if os.path.exists(os.path.join(ROOT, "assets", "avatars", year, p["code"] + ext)):
                    person["avatar"] = f"assets/avatars/{year}/{p['code']}{ext}"
    people = OrderedDict(sorted(people.items(), key=lambda kv: kv[1]["name"].split("[")[0].strip().split()[-1].lower()))
    return meta, conf, talks, recordings, people


def split_name(public_name):
    """'Alan Chalker [Ohio Supercomputer Center]' -> ('Alan Chalker', 'Ohio Supercomputer Center')"""
    m = re.match(r"^(.*?)\s*\[(.*)\]\s*$", public_name)
    return (m.group(1), m.group(2)) if m else (public_name, "")


def fmt_day(d):
    return datetime.strptime(d, "%Y-%m-%d").strftime("%A, %B %-d")


def fmt_duration(hhmm):
    h, m = map(int, hhmm.split(":"))
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def fmt_time(hhmm):
    h, m = map(int, hhmm.split(":"))
    suffix = "am" if h < 12 else "pm"
    h = h % 12 or 12
    return f"{h}:{m:02d} {suffix}"


# ---------- page shell ----------

def page(title, body, depth, description="", nav_year=None, years=YEARS):
    rel = "../" * depth
    links = "".join(f'<a href="{rel}{y}/"{" aria-current=\"page\"" if y == nav_year else ""}>{y}</a>' for y in years)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(description)}">
<link rel="icon" href="{rel}assets/img/GoodIcon.png">
<link rel="stylesheet" href="{rel}assets/style.css">
</head>
<body>
<header class="site-header">
  <a class="brand" href="{rel}"><img src="{rel}assets/img/GoodIcon.png" alt="" width="36" height="36"><span>GOOD <small>Global Open OnDemand Conference</small></span></a>
  <nav aria-label="Conference years">{links}</nav>
</header>
<main>
{body}
</main>
<footer class="site-footer">
  <p>An archive of the Global Open OnDemand (GOOD) conference sites, maintained by the <a href="https://openondemand.org/">Open OnDemand</a> project. The conferences were organized with <a href="https://numfocus.org/">NumFOCUS</a>.</p>
  <p><a href="https://openondemand.org/"><img src="{rel}assets/img/ood-logo.svg" alt="Open OnDemand" height="28"></a></p>
</footer>
</body>
</html>
"""


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------- year pages ----------

def year_index(year, meta, talks, recordings, people):
    n_rec = len(recordings)
    stats = f"{len(talks)} sessions · {len(people)} speakers" + (f" · {n_rec} recordings" if n_rec else "")
    structure = "".join(f"<li><b>{E(s['when'])}</b> {E(s['what'])}</li>" for s in meta["structure"])
    overview = "".join(f"<p>{E(p)}</p>" for p in meta["overview"])
    v = meta["venue"]
    resources = "".join(
        f'<li><a href="{E(r["url"])}">{E(r["label"])}</a>{(" <span class=\"note\">" + E(r["note"]) + "</span>") if r.get("note") else ""}</li>'
        for r in meta["resources"])
    sponsors = ""
    for tier in meta["sponsors"]:
        logos = "".join(
            f'<a href="{E(o["url"])}" title="{E(o["name"])}"><img src="../{E(o["logo"])}" alt="{E(o["name"])}" loading="lazy"></a>'
            for o in tier["orgs"])
        sponsors += f'<div class="tier"><h3>{E(tier["tier"])}</h3><div class="logos">{logos}</div></div>'
    body = f"""
<section class="hero" style="background-image:url('../{E(meta['hero_image'])}')">
  <div class="hero-text">
    <p class="eyebrow">{E(meta['dates'])} · {E(meta['location'])}</p>
    <h1>{E(meta['title'])}</h1>
    <p class="lede">{E(meta['tagline'])}</p>
    <p class="stats">{stats}</p>
    <p class="cta"><a class="button" href="program/">Program</a> <a class="button secondary" href="speakers/">Speakers</a></p>
  </div>
</section>

<section class="two-col">
  <div>
    <h2>About the conference</h2>
    {overview}
    <ul class="structure">{structure}</ul>
  </div>
  <aside>
    <h2>Venue</h2>
    <p><b>{E(v['name'])}</b><br>{E(v['org'])}<br>{E(v['address'])}</p>
    <p>{E(v['thanks'])}</p>
    <p><a href="{E(v['map'])}">Map</a></p>
  </aside>
</section>

<section>
  <h2>Resources</h2>
  <ul class="resources">{resources}</ul>
</section>

<section id="sponsors">
  <h2>Sponsors</h2>
  {sponsors}
  <p class="muted">{E(meta['organized_by'])}</p>
</section>
"""
    return page(f"{meta['title']} · {meta['dates']}", body, 1, meta["tagline"], nav_year=year)


def program_page(year, meta, talks, recordings, people):
    days = OrderedDict()
    for t in talks:
        days.setdefault(t["day"], []).append(t)
    toc = " · ".join(f'<a href="#d{d}">{E(fmt_day(d))}</a>' for d in days)
    body = f"""
<section class="narrow">
  <p class="eyebrow"><a href="../">{E(meta['title'])}</a></p>
  <h1>Program</h1>
  <p class="muted">{E(meta['dates'])} · {E(meta['location'])}. Times are local. Expand a session for its abstract.</p>
  <p class="toc">{toc}</p>
</section>
"""
    for d, items in days.items():
        rows = ""
        for t in items:
            speakers = ", ".join(
                f'<a href="../speakers/#{E(p["code"])}">{E(split_name(p["public_name"])[0])}</a>' for p in t["persons"])
            labels = []
            for x in (t.get("track"), t.get("type")):
                if x and x != "Talk" and norm(x) not in [norm(l) for l in labels]:
                    labels.append(x)
            tags = " ".join(f'<span class="tag">{E(x)}</span>' for x in labels)
            vid = next((recordings[c] for c in t["codes"] if c in recordings), None)
            rec = f' <a class="watch" href="https://vimeo.com/{vid}">Watch recording</a>' if vid else ""
            abstract = md(t.get("abstract")) + (md(t.get("description")) if t.get("description") else "")
            detail = f"<details><summary>Abstract</summary><div class=\"abstract\">{abstract}</div></details>" if abstract.strip() else ""
            rows += f"""
<article class="session" id="{E(t['code'])}">
  <div class="when"><time>{E(fmt_time(t['start']))}</time><span class="dur">{E(fmt_duration(t['duration']))}</span><span class="room">{E(" · ".join(t['rooms']))}</span></div>
  <div class="what">
    <h3>{E(t['title'])}</h3>
    <p class="who">{speakers}</p>
    <p class="meta">{tags}{rec}</p>
    {detail}
  </div>
</article>"""
        body += f'<section class="day" id="d{d}"><h2>{E(fmt_day(d))}</h2>{rows}</section>'
    return page(f"Program · {meta['title']}", body, 2, f"The {meta['title']} program: every session with abstracts and speakers.", nav_year=year)


def speakers_page(year, meta, talks, recordings, people):
    by_code = {t["code"]: t for t in talks}
    cards = ""
    for code, p in people.items():
        name, org = split_name(p["name"])
        img = f'<img src="../../{E(p["avatar"])}" alt="" loading="lazy">' if p.get("avatar") else '<span class="avatar-fallback" aria-hidden="true"></span>'
        sessions = "".join(f'<li><a href="../program/#{E(c)}">{E(by_code[c]["title"])}</a></li>' for c in p["talks"])
        bio = f"<details><summary>Biography</summary>{md(p['bio'])}</details>" if p["bio"].strip() else ""
        cards += f"""
<article class="speaker" id="{E(code)}">
  <div class="avatar">{img}</div>
  <div>
    <h3>{E(name)}</h3>
    <p class="org">{E(org)}</p>
    <ul class="sessions">{sessions}</ul>
    {bio}
  </div>
</article>"""
    body = f"""
<section class="narrow">
  <p class="eyebrow"><a href="../">{E(meta['title'])}</a></p>
  <h1>Speakers</h1>
  <p class="muted">{len(people)} speakers, listed by surname.</p>
</section>
<section class="speakers">{cards}</section>
"""
    return page(f"Speakers · {meta['title']}", body, 2, f"Speakers at {meta['title']}.", nav_year=year)


# ---------- root ----------

def root_index(summaries):
    cards = ""
    for s in summaries:
        m = s["meta"]
        cards += f"""
<a class="year-card" href="{m['year']}/" style="background-image:url('{E(m['hero_image'])}')">
  <div>
    <p class="eyebrow">{E(m['dates'])}</p>
    <h2>{E(m['title'])}</h2>
    <p>{E(m['location'])}</p>
    <p class="stats">{s['stats']}</p>
  </div>
</a>"""
    body = f"""
<section class="narrow intro">
  <h1>Global Open OnDemand Conference</h1>
  <p class="lede">GOOD brings together the users, administrators, and developers of <a href="https://openondemand.org/">Open OnDemand</a> for talks, tutorials, and a Contributor Jam with the core team. These pages archive each year's program, speakers, sponsors, and recordings.</p>
</section>
<section class="years">{cards}</section>
"""
    return page("GOOD Conference Archive", body, 0, "Archive of the Global Open OnDemand (GOOD) conferences: programs, speakers, and recordings.")


# ---------- redirects (old Squarespace paths, per hostname) ----------

OLD_PATHS = {
    "schedule": "program/", "program-2026": "program/", "speakers": "speakers/",
    "about": "", "info": "", "faq": "", "index": "", "home": "",
    "sponsorship-opportunites": "#sponsors", "sponsorship-opportunites-1": "#sponsors",
    "stack-science": "#sponsors", "contributor-jam": "program/",
}


def redirects(summaries):
    lines = ["# Old hostnames serve their year; old Squarespace paths map onto the new pages."]
    for s in summaries:
        m = s["meta"]
        host = m["hostname"]
        for h in (f"https://{host}", f"https://www.{host}"):
            for old, new in OLD_PATHS.items():
                lines.append(f"{h}/{old}  /{m['year']}/{new}  301")
            lines.append(f"{h}/assets/*  /assets/:splat  200")
            lines.append(f"{h}/{m['year']}/*  /{m['year']}/:splat  200")
            lines.append(f"{h}/*  /{m['year']}/:splat  200")
    return "\n".join(lines) + "\n"


# ---------- main ----------

def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    summaries = []
    for year in YEARS:
        meta, conf, talks, recordings, people = load_year(year)
        write(os.path.join(OUT, year, "index.html"), year_index(year, meta, talks, recordings, people))
        write(os.path.join(OUT, year, "program", "index.html"), program_page(year, meta, talks, recordings, people))
        write(os.path.join(OUT, year, "speakers", "index.html"), speakers_page(year, meta, talks, recordings, people))
        stats = f"{len(talks)} sessions · {len(people)} speakers" + (f" · {len(recordings)} recordings" if recordings else "")
        summaries.append({"meta": meta, "stats": stats})
        print(f"{year}: {len(talks)} sessions, {len(people)} speakers, {len(recordings)} recordings")
    write(os.path.join(OUT, "index.html"), root_index(summaries))
    write(os.path.join(OUT, "_redirects"), redirects(summaries))
    print("built", OUT)


if __name__ == "__main__":
    main()
