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
import hashlib
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
LOGO = open(os.path.join(ROOT, "assets", "img", "ood-logo.svg.frag")).read().strip()
CSS_HASH = hashlib.sha1(open(os.path.join(ROOT, "assets", "style.css"), "rb").read()).hexdigest()[:8]
CSS_NAME = f"style.{CSS_HASH}.css"


# ---------- tiny markdown (pretalx abstracts are mostly plain text) ----------

def md(text):
    if not text:
        return ""
    text = text.replace("\r\n", "\n").strip()
    text = E(text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"(?<![\w/\"=>])(https?://[^\s<)\"]+?)([.,;:!?)]*)(?=\s|$|<)", r'<a href="\1">\1</a>\2', text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"<em>\1</em>", text)
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if all(re.match(r"\s*[-*•] ", l) for l in lines):
            items = "".join('<li class="%s">%s</li>' % ("nested" if re.match(r"\s{2,}|\t", l) else "", re.sub(r"^\s*[-*•] ", "", l)) for l in lines)
            out.append("<ul>" + items + "</ul>")
        elif all(re.match(r"\s*\d+[.)] ", l) for l in lines):
            out.append("<ol>" + "".join("<li>%s</li>" % re.sub(r"^\s*\d+[.)] ", "", l) for l in lines) + "</ol>")
        elif len(lines) == 1 and re.match(r"#{1,4} ", lines[0]):
            out.append("<p><strong>%s</strong></p>" % re.sub(r"^#{1,4} ", "", lines[0]))
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
        overrides = meta.get("recording_overrides", {})
        titles = {}
        for t in talks:
            titles.setdefault(norm(t["title"]), []).append(t["code"])
        claimed = set(v for v in overrides.values() if v)
        for c in clips:
            if c["vimeo_id"] in claimed:
                continue
            ct = norm(re.sub(r"\s*-\s*GOOD Conference \d{4}\s*$", "", c["title"]))
            best = max(titles, key=lambda k: difflib.SequenceMatcher(None, ct, k).ratio())
            codes = [k for k in titles[best] if k not in overrides and k not in recordings]
            # an ambiguous title (several talks, no override) is left for a human to settle
            if difflib.SequenceMatcher(None, ct, best).ratio() >= 0.75 and len(codes) == 1:
                recordings[codes[0]] = c["vimeo_id"]
            elif len(codes) > 1:
                print(f"  ambiguous clip {c['vimeo_id']} '{c['title']}' matches {codes}; add a recording_overrides entry")
        for code, vid in overrides.items():
            if vid:
                recordings[code] = vid
            else:
                recordings.pop(code, None)

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
    def sort_key(kv):
        import unicodedata
        surname = kv[1]["name"].split("[")[0].strip().split()[-1]
        return unicodedata.normalize("NFKD", surname).encode("ascii", "ignore").decode().lower()
    people = OrderedDict(sorted(people.items(), key=sort_key))
    return meta, conf, talks, recordings, people


def split_name(public_name):
    """'Alan Chalker [Ohio Supercomputer Center]' -> ('Alan Chalker', 'Ohio Supercomputer Center')"""
    m = re.match(r"^(.*?)\s*\[(.*)\]\s*$", public_name)
    return (m.group(1), m.group(2)) if m else (public_name, "")


def fmt_day(d):
    dt = datetime.strptime(d, "%Y-%m-%d")
    return dt.strftime("%A, %B ") + str(dt.day)


def fmt_duration(hhmm):
    if not hhmm or ":" not in str(hhmm):
        return ""
    h, m = map(int, str(hhmm).split(":")[:2])
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def fmt_time(hhmm):
    h, m = map(int, hhmm.split(":"))
    suffix = "am" if h < 12 else "pm"
    h = h % 12 or 12
    return f"{h}:{m:02d} {suffix}"


# ---------- page shell ----------

SITE = "https://ood-good-conference.netlify.app"


def page(title, body, depth, description="", nav_year=None, years=YEARS, path="/", image=None):
    extra_head = f'<link rel="canonical" href="{SITE}{path}">\n<meta property="og:title" content="{E(title)}">\n<meta property="og:description" content="{E(description)}">\n<meta property="og:type" content="website">\n<meta property="og:url" content="{SITE}{path}">\n'
    if image:
        extra_head += f'<meta property="og:image" content="{SITE}/{image}">\n<link rel="preload" as="image" href="{"../" * depth}{image}">\n'''
    extra_head = extra_head.replace("\n'", "\n")
    rel = "../" * depth or "./"
    links = "".join(f'<a href="{rel}{y}/"{" aria-current=\"page\"" if y == nav_year else ""}>{y}</a>' for y in years)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(description)}">
<link rel="icon" href="{rel}assets/img/GoodIcon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Sans+3:ital,wght@0,400;0,600;0,700;1,400&amp;display=swap">
<link rel="preload" href="{rel}assets/fonts/SerifaStd-Black.woff2" as="font" type="font/woff2" crossorigin>
{extra_head}<link rel="stylesheet" href="{rel}assets/{CSS_NAME}">
</head>
<body>
<header class="site-header">
  <div class="bar">
    <div class="brand">
      <a class="brand-ood" href="https://openondemand.org/" aria-label="Open OnDemand home">{LOGO}</a>
      <a class="brand-good" href="{rel}"><img class="good-logo" src="{rel}assets/img/good-logo-white.png" alt="GOOD: Global Open OnDemand Conference" width="500" height="164"></a>
    </div>
    <nav aria-label="Conference years and related sites">{links}<span class="nav-sep" aria-hidden="true"></span><a class="ext" href="https://openondemand.connectci.org/events">Events</a><a class="ext" href="https://ondemand.connectci.org">Community Hub</a></nav>
  </div>
</header>
<main>
{body}
</main>
<footer class="site-footer">
  <div class="bar">
    <div>
      <p>An archive of the Global Open OnDemand (GOOD) conference sites, maintained by the <a href="https://openondemand.org/">Open OnDemand</a> project.</p>
      <p>The conferences were organized with <a href="https://numfocus.org/">NumFOCUS</a>.</p>
    </div>
    <a href="https://openondemand.org/" aria-label="Open OnDemand">{LOGO}</a>
  </div>
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
    def rurl(u):
        return u if u.startswith("http") else "../" + u
    resources = "".join(
        f'<li><a href="{E(rurl(r["url"]))}">{E(r["label"])}</a>{(" <span class=\"note\">" + E(r["note"]) + "</span>") if r.get("note") else ""}</li>'
        for r in meta["resources"])
    topics = ""
    if meta.get("conference_topics"):
        topics = "<div class=\"topics-box\"><h3>Conference topics</h3><ul class=\"topics\">" + "".join(f"<li>{E(x)}</li>" for x in meta["conference_topics"]) + "</ul></div>"
    photo = ""
    if meta.get("photo"):
        photo = f'<figure class="photo"><img src="../{E(meta["photo"]["src"])}" alt="{E(meta["photo"]["alt"])}" loading="lazy"></figure>'
    committee = ""
    if meta.get("committee"):
        groups = "".join(
            f'<div class="role"><h3>{E(g["role"])}</h3><ul>' + "".join(f"<li>{E(p)}</li>" for p in g["people"]) + "</ul></div>"
            for g in meta["committee"])
        committee = f'<section id="committee"><h2>Organizing committee</h2><div class="committee">{groups}</div></section>'
    policies = ""
    if meta.get("accessibility") or meta.get("code_of_conduct"):
        acc = "".join(f"<p>{E(p)}</p>" for p in meta.get("accessibility", []))
        coc = f'<p>{E(meta["code_of_conduct"])}</p>' if meta.get("code_of_conduct") else ""
        policies = f'<section class="two-col policies"><div><h2>Accessibility and accommodation</h2>{acc}</div><div><h2>Code of conduct</h2>{coc}</div></section>'
    memorial = ""
    if meta.get("memorial"):
        m = meta["memorial"]
        paras = "".join(f"<p>{E(p)}</p>" for p in m["paragraphs"])
        memorial = f"""<section class="memorial" id="memorial">
  <div class="memorial-head">
    <img src="../{E(m["photo"])}" alt="Chris Blanton" loading="lazy">
    <div><h2>{E(m["title"])}</h2><p class="lede">{E(m["intro"])}</p></div>
  </div>
  <details><summary>Remembering Chris</summary><div class="narrow">{paras}</div></details>
</section>"""
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
    {topics}
  </div>
  <div class="panel">
    <h2>Venue</h2>
    <p><b>{E(v['name'])}</b><br>{E(v['org'])}<br>{E(v['address'])}</p>
    <p>{E(v['thanks'])}</p>
    <p><a href="{E(v['map'])}">Map of the venue</a></p>
  </div>
</section>

{photo}

<section>
  <h2>Resources</h2>
  <ul class="resources">{resources}</ul>
</section>

{policies}

{committee}

{memorial}

<section id="sponsors">
  <h2>Sponsors</h2>
  {sponsors}
  <p class="muted">{E(meta['organized_by'])}</p>
</section>
"""
    return page(f"{meta['title']} · {meta['dates']}", body, 1, meta["tagline"], nav_year=year, path=f"/{year}/", image=meta["hero_image"])


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
            for tag, prefixes in meta.get("session_tags", {}).items():
                if any(norm(t["title"]).startswith(norm(p)) for p in prefixes):
                    labels.append(tag)
            for x in (t.get("track"), t.get("type")):
                if x and x != "Talk" and norm(x) not in [norm(l) for l in labels]:
                    labels.append(x)
            tags = " ".join(f'<span class="tag">{E(x)}</span>' for x in labels)
            vid = next((recordings[c] for c in t["codes"] if c in recordings), None)
            rec = f' <a class="watch" href="https://vimeo.com/{vid}">Watch recording<span class="visually-hidden"> of {E(t["title"])}</span></a>' if vid else ""
            abstract = md(t.get("abstract")) + (md(t.get("description")) if t.get("description") else "")
            detail = f"<details><summary>Abstract<span class=\"visually-hidden\"> for {E(t['title'])}</span></summary><div class=\"abstract\">{abstract}</div></details>" if abstract.strip() else ""
            rows += f"""
<article class="session" id="{E(t['code'])}">{"".join(f'<span id="{E(c)}"></span>' for c in t['codes'][1:])}
  <div class="when"><time>{E(fmt_time(t['start']))}</time><span class="dur">{E(fmt_duration(t['duration']))}</span><span class="room">{E(" · ".join(t['rooms']))}</span></div>
  <div class="what">
    <h3>{E(t['title'])}</h3>
    <p class="who">{speakers}</p>
    {("<p class=\"meta\">" + tags + rec + "</p>") if (tags or rec) else ""}
    {detail}
  </div>
</article>"""
        body += f'<section class="day" id="d{d}"><h2>{E(fmt_day(d))}</h2>{rows}</section>'
    return page(f"Program · {meta['title']}", body, 2, f"The {meta['title']} program: every session with abstracts and speakers.", nav_year=year, path=f"/{year}/program/")


def speakers_page(year, meta, talks, recordings, people):
    by_code = {t["code"]: t for t in talks}
    cards = ""
    for code, p in people.items():
        name, org = split_name(p["name"])
        img = f'<img src="../../{E(p["avatar"])}" alt="" loading="lazy">' if p.get("avatar") else '<span class="avatar-fallback" aria-hidden="true"></span>'
        sessions = "".join(f'<li><a href="../program/#{E(c)}">{E(by_code[c]["title"])}</a></li>' for c in p["talks"])
        bio = f"<details><summary>Biography<span class=\"visually-hidden\"> of {E(name)}</span></summary>{md(p['bio'])}</details>" if p["bio"].strip() else ""
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
<section class="speakers" aria-labelledby="all-speakers"><h2 id="all-speakers" class="visually-hidden">All speakers</h2>{cards}</section>
"""
    return page(f"Speakers · {meta['title']}", body, 2, f"Speakers at {meta['title']}.", nav_year=year, path=f"/{year}/speakers/")


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
  <h1><img class="good-logo-color" src="assets/img/good-logo-color.png" alt="GOOD: Global Open OnDemand Conference" width="500" height="164"></h1>
  <p class="lede">GOOD brings together the users, administrators, and developers of <a href="https://openondemand.org/">Open OnDemand</a> for talks, tutorials, and a Contributor Jam with the core team. These pages archive each year's program, speakers, sponsors, and recordings.</p>
</section>
<section class="years">{cards}</section>
"""
    return page("GOOD Conference Archive", body, 0, "Archive of the Global Open OnDemand (GOOD) conferences: programs, speakers, and recordings.", path="/")


# ---------- redirects (old Squarespace paths, per hostname) ----------

OLD_PATHS = {
    "schedule": "program/", "speakers": "speakers/",
    "about": "#committee", "info": "#committee", "faq": "", "index": "", "home": "",
    "sponsorship-opportunites": "#sponsors", "contributor-jam": "program/",
}


def redirects(summaries):
    lines = ["# Old hostnames serve their year; old Squarespace paths map onto the new pages."]
    for s in summaries:
        m = s["meta"]
        host = m.get("hostname")
        if not host:
            continue
        paths = dict(OLD_PATHS, **m.get("old_paths", {}))
        for h in (f"https://{host}", f"https://www.{host}"):
            lines.append(f"{h}/  /{m['year']}/  301")
            for old, new in paths.items():
                lines.append(f"{h}/{old}  /{m['year']}/{new}  301")
            lines.append(f"{h}/*  /{m['year']}/:splat  200")
    return "\n".join(lines) + "\n"


# ---------- main ----------

def check_assets(meta):
    paths = [meta.get("hero_image")] + [o["logo"] for t in meta["sponsors"] for o in t["orgs"]]
    if meta.get("photo"):
        paths.append(meta["photo"]["src"])
    if meta.get("memorial"):
        paths.append(meta["memorial"]["photo"])
    paths += [r["url"] for r in meta["resources"] if not r["url"].startswith("http")]
    missing = [p for p in paths if p and not os.path.exists(os.path.join(ROOT, p))]
    if missing:
        raise SystemExit(f"{meta['year']}: missing asset files: {missing}")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"), ignore=shutil.ignore_patterns("*.frag"))
    os.rename(os.path.join(OUT, "assets", "style.css"), os.path.join(OUT, "assets", CSS_NAME))
    summaries = []
    for year in YEARS:
        meta, conf, talks, recordings, people = load_year(year)
        check_assets(meta)
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
