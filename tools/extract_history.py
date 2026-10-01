#!/usr/bin/env python3
"""Parse the raw source cache into tools/data/player_seasons.json.gz.

Sources (fetched by tools/fetch_sources.py into /tmp/nfldata):
  * footballdb.com team-season roster pages (jersey, listed pos, G, GS) 1960-2025
  * footballdb.com team-season stats pages 1960-1998 (passing, rushing, receiving,
    returns, kicking, punting, interceptions / sacks)
  * footballdb.com AP All-Pro (NFL 1960-2025) and AP All-AFL (1960-69) teams, HOF list
  * Wikipedia Pro Bowl / AFL All-Star rosters (wikitext)
  * nflverse rosters 1960-2025 (season-specific depth-chart position, headshot)
  * nflverse player stats 1999-2025
  * Wikidata CB / S labels (name + birth date) to split generic "DB"s

Every row in the output is a real player on a real team-season roster.  Stats are
copied from the source tables; nothing is estimated.
"""
from __future__ import annotations

import csv
import glob
import gzip
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import htmltables  # noqa: E402

CACHE = Path("/tmp/nfldata")
FDB = CACHE / "fdb"
AWARDS = CACHE / "fdb_awards"
WIKI = CACHE / "wiki"
OUT = HERE / "data" / "player_seasons.json.gz"

FIRST, LAST = 1960, 2025

# ---------------------------------------------------------------- teams
SLUG_TEAM = {
    "arizona-cardinals": "ARI", "st-louis-cardinals": "ARI", "phoenix-cardinals": "ARI", "chicago-cardinals": "ARI",
    "atlanta-falcons": "ATL", "baltimore-ravens": "BAL", "buffalo-bills": "BUF", "carolina-panthers": "CAR",
    "chicago-bears": "CHI", "cincinnati-bengals": "CIN", "cleveland-browns": "CLE", "dallas-cowboys": "DAL",
    "denver-broncos": "DEN", "detroit-lions": "DET", "green-bay-packers": "GB", "houston-texans": "HOU",
    "indianapolis-colts": "IND", "baltimore-colts": "IND", "jacksonville-jaguars": "JAX",
    "kansas-city-chiefs": "KC", "dallas-texans": "KC",
    "los-angeles-chargers": "LAC", "san-diego-chargers": "LAC",
    "los-angeles-rams": "LAR", "st-louis-rams": "LAR",
    "las-vegas-raiders": "LV", "oakland-raiders": "LV", "los-angeles-raiders": "LV",
    "miami-dolphins": "MIA", "minnesota-vikings": "MIN",
    "new-england-patriots": "NE", "boston-patriots": "NE", "new-orleans-saints": "NO",
    "new-york-giants": "NYG", "new-york-jets": "NYJ", "new-york-titans": "NYJ",
    "philadelphia-eagles": "PHI", "pittsburgh-steelers": "PIT", "seattle-seahawks": "SEA",
    "san-francisco-49ers": "SF", "tampa-bay-buccaneers": "TB",
    "tennessee-titans": "TEN", "houston-oilers": "TEN", "tennessee-oilers": "TEN",
    "washington-redskins": "WAS", "washington-football-team": "WAS", "washington-commanders": "WAS",
    "washington": "WAS",
}


def nflverse_team(code: str, year: int) -> str | None:
    c = (code or "").upper()
    fixed = {
        "NYT": "NYJ", "NYJ": "NYJ", "BOS": "NE", "NE": "NE", "TEX": "KC", "KC": "KC", "COW": "DAL", "DAL": "DAL",
        "CHR": "LAC", "SD": "LAC", "LAC": "LAC", "RAM": "LAR", "LAR": "LAR", "RAI": "LV", "OAK": "LV", "LV": "LV",
        "PHO": "ARI", "ARI": "ARI", "IND": "IND", "TEN": "TEN", "ATL": "ATL", "BUF": "BUF", "CAR": "CAR",
        "CHI": "CHI", "CIN": "CIN", "CLE": "CLE", "DEN": "DEN", "DET": "DET", "GB": "GB", "JAX": "JAX",
        "MIA": "MIA", "MIN": "MIN", "NO": "NO", "NYG": "NYG", "PHI": "PHI", "PIT": "PIT", "SEA": "SEA",
        "SF": "SF", "TB": "TB", "WAS": "WAS",
    }
    if c == "STL":
        return "LAR" if year >= 1995 else "ARI"
    if c == "HOU":
        return "HOU" if year >= 2002 else "TEN"
    if c == "BAL":
        return "BAL" if year >= 1996 else "IND"
    if c == "LA":
        return "LAR"  # nflverse uses RAI for the LA Raiders and CHR for the 1960 LA Chargers
    return fixed.get(c)


def season_games(year: int, league: str = "nfl") -> int:
    if year == 1960 and league == "nfl":
        return 12
    if year <= 1977:
        return 14
    if year == 1982:
        return 9
    if year == 1987:
        return 15
    if year <= 2020:
        return 16
    return 17


# ---------------------------------------------------------------- names
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.I)


def norm(name: str) -> str:
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    n = n.lower().replace(".", " ").replace("'", "").replace("’", "").replace("-", " ")
    n = SUFFIX.sub(" ", n)
    n = re.sub(r"[^a-z ]", " ", n)
    parts = n.split()
    out, buf = [], ""
    for p in parts:  # collapse spaced initials "l c greenwood" -> "lc greenwood"
        if len(p) == 1:
            buf += p
            continue
        if buf:
            out.append(buf)
            buf = ""
        out.append(p)
    if buf:
        out.append(buf)
    return " ".join(out)


def last_name(name: str) -> str:
    p = norm(name).split()
    return p[-1] if p else ""


def num(s, default=0.0):
    s = str(s or "").replace(",", "").replace("t", "").strip()
    if s in ("", "--", "-"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def frac(s):
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)", str(s or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def pid(href: str | None) -> str | None:
    if not href:
        return None
    m = re.search(r"/players/([a-z0-9-]+)", href)
    return m.group(1) if m else None


# ---------------------------------------------------------------- footballdb rosters & stats
def parse_roster(path: Path):
    rows = []
    for t in htmltables.tables(path.read_text(errors="ignore")):
        if "Roster" not in t["title"]:
            continue
        hdr = [c[0] for c in t["rows"][0]]
        ix = {h: i for i, h in enumerate(hdr)}
        for r in t["rows"][1:]:
            if len(r) < len(hdr):
                continue
            name, href = r[ix["Player"]][0], r[ix["Player"]][1]
            if not pid(href):
                continue
            j = r[ix["#"]][0].strip()
            rows.append({
                "id": pid(href), "name": name.strip(),
                "jersey": int(j) if j.isdigit() else None,
                "fpos": r[ix["Pos"]][0].strip().upper(),
                "g": int(num(r[ix["G"]][0])), "gs": (None if r[ix["GS"]][0].strip() in ("--", "") else int(num(r[ix["GS"]][0]))),
            })
    return rows


def _sec(tables, title):
    for t in tables:
        if t["title"].strip().lower() == title.lower():
            hdr = None
            for r in t["rows"]:
                if r and r[0][0] == "Player":
                    hdr = [c[0] for c in r]
                    break
            if not hdr:
                continue
            out = []
            for r in t["rows"]:
                if not r or r[0][2] != "td" or not pid(r[0][1]):
                    continue
                d = {}
                for i in range(min(len(hdr), len(r))):
                    d.setdefault(hdr[i], r[i][0])  # first occurrence wins (e.g. punting Yds vs opp-return Yds)
                out.append((pid(r[0][1]), d, hdr))
            return out
    return []


def parse_stats(path: Path):
    tabs = htmltables.tables(path.read_text(errors="ignore"))
    st = defaultdict(dict)
    for p, d, _ in _sec(tabs, "Passing"):
        st[p].update(pa_att=num(d.get("Att")), pa_cmp=num(d.get("Cmp")), pa_yds=num(d.get("Yds")),
                     pa_td=num(d.get("TD")), pa_int=num(d.get("Int")))
    for p, d, _ in _sec(tabs, "Rushing"):
        st[p].update(ru_att=num(d.get("Att")), ru_yds=num(d.get("Yds")), ru_td=num(d.get("TD")))
    for p, d, _ in _sec(tabs, "Receiving"):
        st[p].update(rec=num(d.get("Rec")), rec_yds=num(d.get("Yds")), rec_td=num(d.get("TD")))
    for p, d, _ in _sec(tabs, "Kickoff Returns"):
        st[p].update(kr=num(d.get("Num")), kr_yds=num(d.get("Yds")), kr_td=num(d.get("TD")))
    for p, d, _ in _sec(tabs, "Punt Returns"):
        st[p].update(pr=num(d.get("Num")), pr_yds=num(d.get("Yds")), pr_td=num(d.get("TD")))
    for p, d, _ in _sec(tabs, "Punting"):
        st[p].update(punts=num(d.get("Punts")), punt_yds=num(d.get("Yds")), punt_avg=num(d.get("Avg")))
    for p, d, _ in _sec(tabs, "Kicking"):
        xm, xa = frac(d.get("PAT"))
        fm, fa = frac(d.get("FG"))
        st[p].update(xpm=xm, xpa=xa, fgm=fm, fga=fa)
    for p, d, hdr in _sec(tabs, "Defense"):
        # Interceptions: Int Yds Avg Lg TD | Sacks: Sack SkYd
        st[p].update(d_int=num(d.get("Int")))
        if "Sack" in d and d.get("Sack") not in ("--", ""):
            st[p]["d_sack"] = num(d.get("Sack"))
    return st


# ---------------------------------------------------------------- honors
def parse_allpro():
    """{(fdb_id, year): best} best = 1 (AP 1st team) or 2 (AP 2nd team)."""
    hon = {}
    pos_of = {}
    for f in glob.glob(str(AWARDS / "ap-*-team_*.html")):
        y = int(re.search(r"_(\d{4})\.html", f).group(1))
        for t in htmltables.tables(Path(f).read_text(errors="ignore")):
            title = t["title"].lower()
            lvl = 1 if title.startswith("first") else 2 if title.startswith("second") else None
            if not lvl:
                continue
            for r in t["rows"]:
                if len(r) < 3 or r[1][2] != "td":
                    continue
                p = pid(r[1][1])
                if not p:
                    continue
                k = (p, y)
                hon[k] = min(hon.get(k, 9), lvl)
                pos_of[k] = r[0][0]
    return hon, pos_of


def parse_hof():
    f = AWARDS / "pro-football-hall-of-fame.html"
    ids = set()
    if f.exists():
        for m in re.finditer(r'href="/players/([a-z0-9-]+)"', f.read_text(errors="ignore")):
            ids.add(m.group(1))
    return ids


def parse_alldecade():
    ids = {}
    for f in glob.glob(str(AWARDS / "nfl-*-all-decade-team.html")):
        dec = re.search(r"nfl-(\d{4})s", f).group(1) + "s"
        for m in re.finditer(r'href="/players/([a-z0-9-]+)"', Path(f).read_text(errors="ignore")):
            ids.setdefault(m.group(1), set()).add(dec)
    return ids


WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def probowl_names():
    """{season: set(norm names)} of Pro Bowl / AFL All-Star selections (incl. alternates listed)."""
    idx = json.loads((WIKI / "probowl_index.json").read_text()) if (WIKI / "probowl_index.json").exists() else {}
    out = {}
    for season, titles in idx.items():
        names = set()
        for t in titles:
            p = WIKI / (t.replace(" ", "_") + ".wikitext")
            if not p.exists():
                continue
            txt = p.read_text(errors="ignore")
            # only the roster part of the article
            m = re.search(r"==\s*(Rosters?|AFC roster|Roster|Teams?|All-Star teams|Players|Selections?|NFC roster|AFC|Eastern)[^=]*==", txt)
            body = txt[m.start():] if m else txt
            for lm in WIKILINK.finditer(body):
                target = lm.group(1)
                if any(w in target.lower() for w in ("season", "football", "team", "bowl", "position", "quarterback",
                                                    "back", "receiver", "end", "tackle", "guard", "center", "linebacker",
                                                    "safety", "kicker", "punter", "returner", "category:", "file:")) and "(" not in target:
                    continue
                disp = lm.group(2) or re.sub(r"\s*\(.*\)$", "", target)
                if len(disp.split()) >= 2:
                    names.add(norm(disp))
        if names:
            out[int(season)] = names
    return out


# ---------------------------------------------------------------- nflverse
NV_POS = {
    "QB": "QB", "RB": "RB", "HB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
    "OT": "OT", "T": "OT", "LT": "OT", "RT": "OT", "G": "OG", "OG": "OG", "LG": "OG", "RG": "OG", "C": "C",
    "DE": "DE", "LE": "DE", "RE": "DE", "DT": "DT", "NT": "DT",
    "OLB": "OLB", "WLB": "OLB", "SLB": "OLB", "LOLB": "OLB", "ROLB": "OLB",
    "MLB": "MLB", "ILB": "MLB", "LILB": "MLB", "RILB": "MLB", "LB": "LB",
    "CB": "CB", "LCB": "CB", "RCB": "CB", "S": "S", "SAF": "S", "SS": "SS", "FS": "FS", "DB": "DB",
    "K": "K", "PK": "K", "P": "P",
}
FDB_POS = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE", "OT": "OT", "T": "OT",
           "OG": "OG", "G": "OG", "C": "C", "DE": "DE", "DT": "DT", "NT": "DT", "LB": "LB", "ILB": "MLB",
           "MLB": "MLB", "OLB": "OLB", "DB": "DB", "CB": "CB", "S": "S", "SS": "SS", "FS": "FS", "K": "K", "P": "P"}


def load_nflverse_rosters():
    """{(team, year): [rows]} with norm name, dob, nv pos."""
    by = defaultdict(list)
    for y in range(FIRST, LAST + 1):
        p = CACHE / "rosters" / f"roster_{y}.csv"
        if not p.exists():
            continue
        with p.open(newline="", encoding="utf-8", errors="ignore") as f:
            for r in csv.DictReader(f):
                team = nflverse_team(r.get("team"), y)
                if not team:
                    continue
                dpos = (r.get("depth_chart_position") or "").upper()
                gpos = (r.get("position") or "").upper()
                pos = NV_POS.get(dpos) or NV_POS.get(gpos)
                if gpos == "OL" and dpos in ("", "OL"):
                    pos = "OL"
                if gpos == "DL" and dpos in ("", "DL"):
                    pos = "DL"
                photo = r.get("headshot_url") or ""
                jersey = r.get("jersey_number") or ""
                by[(team, y)].append({
                    "name": r.get("full_name") or "", "n": norm(r.get("full_name") or ""),
                    "first": norm(r.get("first_name") or ""), "last": norm(r.get("last_name") or ""),
                    "dob": (r.get("birth_date") or "")[:10], "pos": pos,
                    "photo": photo if photo.startswith("http") else None,
                    "jersey": int(float(jersey)) if jersey not in ("", "NA", "0") and jersey.replace(".", "").isdigit() else None,
                    "gsis": r.get("gsis_id") or "", "pfr": r.get("pfr_id") or "",
                })
    return by


def load_nflverse_stats():
    by = {}
    for y in range(1999, LAST + 1):
        p = CACHE / "stats" / f"stats_player_reg_{y}.csv"
        if not p.exists():
            continue
        with p.open(newline="", encoding="utf-8", errors="ignore") as f:
            for r in csv.DictReader(f):
                team = nflverse_team(r.get("recent_team") or r.get("team") or "", y)
                if not team:
                    continue
                n = norm(r.get("player_display_name") or r.get("player_name") or "")
                g = lambda k: num(r.get(k))
                by[(team, y, n)] = {
                    "pa_att": g("attempts"), "pa_cmp": g("completions"), "pa_yds": g("passing_yards"),
                    "pa_td": g("passing_tds"), "pa_int": g("passing_interceptions") or g("interceptions"),
                    "ru_att": g("carries"), "ru_yds": g("rushing_yards"), "ru_td": g("rushing_tds"),
                    "rec": g("receptions"), "rec_yds": g("receiving_yards"), "rec_td": g("receiving_tds"),
                    "d_sack": g("def_sacks"), "d_int": g("def_interceptions"),
                    "d_tkl": g("def_tackles_solo") + g("def_tackle_assists") if (r.get("def_tackles_solo") or r.get("def_tackle_assists")) else g("def_tackles"),
                    "d_tfl": g("def_tackles_for_loss"), "d_pd": g("def_pass_defended"), "d_ff": g("def_fumbles_forced"),
                    "fgm": g("fg_made"), "fga": g("fg_att"), "xpm": g("pat_made"), "xpa": g("pat_att"),
                    "punts": g("pt_att") if r.get("pt_att") is not None else 0, "punt_yds": g("pt_yards"),
                    "kr": g("kickoff_returns"), "kr_yds": g("kickoff_return_yards"),
                    "pr": g("punt_returns"), "pr_yds": g("punt_return_yards"), "st_td": g("special_teams_tds"),
                    "games": g("games"), "photo": r.get("headshot_url") or None,
                }
    return by


def load_wiki_titles():
    """(norm name, dob) -> enwiki title, only when unique."""
    p = CACHE / "wikidata_enwiki_dob.json"
    m = defaultdict(set)
    if p.exists():
        for r in json.loads(p.read_text()):
            base = re.sub(r"\s*\(.*\)$", "", r["title"])
            m[(norm(base), r["dob"])].add(r["title"])
    return {k: next(iter(v)) for k, v in m.items() if len(v) == 1}


def load_wikidata_db():
    p = CACHE / "wikidata_db_pos.json"
    out = defaultdict(set)
    if p.exists():
        for r in json.loads(p.read_text()):
            out[(norm(r["name"]), r.get("dob") or "")].add(r["pos"])
            out[(norm(r["name"]), "")].add(r["pos"])
    return out


# ---------------------------------------------------------------- main
def match_nv(row, nv_rows):
    n = norm(row["name"])
    exact = [r for r in nv_rows if r["n"] == n]
    if len(exact) == 1:
        return exact[0]
    ln = last_name(row["name"])
    fi = n[:1]
    cands = [r for r in nv_rows if r["last"] == ln or r["n"].split()[-1:] == [ln]]
    if len(cands) == 1:
        return cands[0]
    c2 = [r for r in cands if r["n"][:1] == fi or r["first"][:1] == fi]
    if len(c2) == 1:
        return c2[0]
    return None


def main():
    nv = load_nflverse_rosters()
    nvs = load_nflverse_stats()
    wd = load_wikidata_db()
    wt = load_wiki_titles()
    allpro, ap_pos = parse_allpro()
    hof = parse_hof()
    alldec = parse_alldecade()
    pb = probowl_names()
    print("nflverse team-seasons", len(nv), "nv stats", len(nvs), "allpro", len(allpro), "hof", len(hof), "pb seasons", len(pb))

    out = []
    seen_ts = set()
    missing_stats = []
    for f in sorted(glob.glob(str(FDB / "roster_*.html"))):
        m = re.match(r".*/roster_(\d{4})_(nfl|afl)_([a-z0-9-]+)\.html$", f)
        y, lg, slug = int(m.group(1)), m.group(2), m.group(3)
        team = SLUG_TEAM.get(slug)
        if not team:
            print("unmapped slug", slug)
            continue
        if (team, y) in seen_ts:
            continue
        seen_ts.add((team, y))
        roster = parse_roster(Path(f))
        stats = {}
        sp = FDB / f"stats_{y}_{lg}_{slug}.html"
        if y <= 1998:
            if sp.exists():
                stats = parse_stats(sp)
            else:
                missing_stats.append((team, y))
        nv_rows = nv.get((team, y), [])
        for r in roster:
            mv = match_nv(r, nv_rows)
            rec = {"id": r["id"], "name": r["name"], "team": team, "year": y, "lg": lg,
                   "jersey": r["jersey"], "g": r["g"], "gs": r["gs"], "fpos": FDB_POS.get(r["fpos"], r["fpos"]),
                   "nvpos": mv["pos"] if mv else None, "dob": mv["dob"] if mv else "",
                   "photo": mv["photo"] if mv else None}
            if y <= 1998:
                rec["st"] = {k: v for k, v in stats.get(r["id"], {}).items() if v}
            else:
                s = nvs.get((team, y, norm(r["name"])))
                if s is None and mv:
                    s = nvs.get((team, y, mv["n"]))
                if s:
                    rec["photo"] = rec["photo"] or s.get("photo")
                    rec["st"] = {k: v for k, v in s.items() if k not in ("photo",) and v}
                else:
                    rec["st"] = {}
            ap = allpro.get((r["id"], y))
            if ap:
                rec["ap"] = ap
                rec["ap_pos"] = ap_pos.get((r["id"], y))
            if y in pb and norm(r["name"]) in pb[y]:
                rec["pb"] = 1
            if rec["dob"]:
                w = wt.get((norm(r["name"]), rec["dob"]))
                if w:
                    rec["wiki"] = w
            if r["id"] in hof:
                rec["hof"] = 1
            if r["id"] in alldec:
                rec["alldec"] = sorted(alldec[r["id"]])
            out.append(rec)

    # ---------- resolve position per player-season
    career = defaultdict(Counter)
    for rec in out:
        p = rec["nvpos"]
        if p:
            career[rec["id"]][p] += 1
    unresolved = Counter()
    for rec in out:
        p = rec["nvpos"] or rec["fpos"]
        if p == "OL":
            p = rec["fpos"] if rec["fpos"] in ("OT", "OG", "C") else None
        if p == "DL":
            p = rec["fpos"] if rec["fpos"] in ("DE", "DT") else None
        if p == "OE":  # 1960s "offensive end": take nflverse WR/TE label from any season
            c = career[rec["id"]]
            p = "WR" if c["WR"] >= c["TE"] and c["WR"] else "TE" if c["TE"] else None
        if p == "DB":
            c = career[rec["id"]]
            spec = {k: v for k, v in c.items() if k in ("CB", "S", "SS", "FS")}
            if spec:
                cb = spec.get("CB", 0)
                sf = spec.get("S", 0) + spec.get("SS", 0) + spec.get("FS", 0)
                if cb > sf:
                    p = "CB"
                elif sf > cb:
                    ss, fs = spec.get("SS", 0), spec.get("FS", 0)
                    p = "SS" if ss > fs and ss > spec.get("S", 0) else "FS" if fs > ss and fs > spec.get("S", 0) else "S"
            if p == "DB":
                w = wd.get((norm(rec["name"]), rec["dob"])) or (wd.get((norm(rec["name"]), "")) if not rec["dob"] else None)
                if w:
                    w = w - {"DB"}
                    if w == {"CB"}:
                        p = "CB"
                    elif w and "CB" not in w:
                        p = "SS" if w == {"SS"} else "FS" if w == {"FS"} else "S"
            if p == "DB":
                unresolved["DB"] += 1
        if p == "LB":
            c = career[rec["id"]]
            o, mm = c["OLB"], c["MLB"]
            if o > mm:
                p = "OLB"
            elif mm > o:
                p = "MLB"
        rec["pos"] = p
    # ---------- Wikipedia infobox facts (pre-1975): AFL All-Star / Pro Bowl years, single listed jersey,
    # and the listed position to split generic DB / LB / OL / DL labels.
    ib_path = HERE / "data" / "wiki_infobox.json"
    ib = json.loads(ib_path.read_text()) if ib_path.exists() else {}
    IB_POS = {"cornerback": "CB", "safety": "S", "free safety": "FS", "strong safety": "SS",
              "middle linebacker": "MLB", "outside linebacker": "OLB", "inside linebacker": "MLB",
              "defensive end": "DE", "defensive tackle": "DT", "nose tackle": "DT",
              "offensive tackle": "OT", "tackle": "OT", "guard": "OG", "offensive guard": "OG", "center": "C"}
    n_afl = n_pb = n_j = n_pos = 0
    for rec in out:
        f = ib.get(rec.get("wiki") or "")
        if not f:
            continue
        if rec["lg"] == "afl" and rec["year"] in f.get("afl_as", []):
            rec["pb"] = 1
            rec["afl_as"] = 1
            n_afl += 1
        elif rec["year"] <= 1974 and rec["year"] in f.get("pb", []) and not rec.get("pb"):
            rec["pb"] = 1
            n_pb += 1
        if rec.get("jersey") is None and rec["year"] < 1975:
            if len(f.get("num", [])) == 1:
                rec["jersey"] = f["num"][0]
                n_j += 1
            elif rec["team"] in f.get("team_num", {}):
                rec["jersey"] = f["team_num"][rec["team"]]
                n_j += 1
        ip = IB_POS.get((f.get("pos") or "").lower())
        if ip and rec["pos"] in (None, "DB", "LB", "OL", "DL", "S"):
            fam = {"DB": {"CB", "S", "FS", "SS"}, "S": {"S", "FS", "SS"}, "LB": {"MLB", "OLB"},
                   "OL": {"OT", "OG", "C"}, "DL": {"DE", "DT"}, None: set(IB_POS.values())}[rec["pos"]]
            if ip in fam and ip != rec["pos"]:
                rec["pos"] = ip
                n_pos += 1
    print("infobox: afl all-star seasons", n_afl, "extra pro bowls", n_pb, "jerseys", n_j, "positions", n_pos)
    unresolved["DB"] = sum(1 for r in out if r["pos"] == "DB")
    print("unresolved generic DB seasons", unresolved["DB"])
    print("team-seasons", len(seen_ts), "player-seasons", len(out), "missing stats pages", len(missing_stats))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    slim = []
    for r in out:
        r = {k: v for k, v in r.items() if v not in (None, "", {}, [])}
        slim.append(r)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(slim, fh, separators=(",", ":"))
    print("wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
