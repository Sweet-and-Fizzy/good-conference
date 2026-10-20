# GOOD conference archive

Static archive of the Global Open OnDemand (GOOD) conference sites: program,
speakers, sponsors, and recordings for each year. Replaces the Squarespace
sites at conference2025.openondemand.org and good2026.openondemand.org.

No framework, no dependencies. `build.py` (Python 3 standard library) turns
`data/` into `site/`; Netlify runs it on every push.

## Layout

    data/<year>.json              hand-written: dates, venue, overview, sponsors, resources
    data/good<year>-schedule.json pretalx schedule export, verbatim
    data/showcase-<year>-clips.json optional: Vimeo showcase clips, matched to talks by title
    assets/                       stylesheet, logos, avatars, photos (copied into site/assets)
    build.py                      generator
    site/                         output (git-ignored)

## Build and preview

    python3 build.py
    python3 -m http.server 8000 --directory site

## Adding a year

1. Export the schedule from pretalx (`/schedule/export/schedule.json`) into
   `data/good<year>-schedule.json`.
2. Write `data/<year>.json` following the existing ones. Sponsor logos and a
   hero photo go under `assets/`.
3. If there is a Vimeo showcase, save its clips as
   `data/showcase-<year>-clips.json` (`[{"vimeo_id": ..., "title": ...}]`) and
   name it in `recordings_source`. Recordings are matched to talks by title.
4. Speaker avatars: download from the pretalx `avatar` URLs into
   `assets/avatars/<year>/<speaker code>.<ext>`.
5. Add the year's hostname to `hostname` in the JSON; `build.py` writes the
   `_redirects` rules that serve that hostname from the year's folder and map
   the old Squarespace paths onto the new pages.

## Hosting

Netlify, publish directory `site/`. Each year's old hostname is a domain
alias on the site; `_redirects` routes by hostname. Speaker photos and
abstracts are © their authors; conference photos and logos belong to the
conference sponsors and hosts.

## Review deployment

While under review the site is at <https://ood-good-conference.netlify.app>.
Netlify builds and deploys every push to `main`, and pull requests get deploy
previews. When the old hostnames are added as domain aliases, the rules in
`site/_redirects` route each to its year.
