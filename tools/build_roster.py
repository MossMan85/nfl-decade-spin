#!/usr/bin/env python3
"""Build rosterDB (nfl-data.js) for NFL Decade Spin from real player-seasons.

Pipeline (all steps reproducible):
  1. tools/fetch_sources.py   -> raw cache in /tmp/nfldata (footballdb, nflverse, Wikipedia, Wikidata)
  2. tools/extract_history.py -> tools/data/player_seasons.json.gz (committed snapshot)
  3. tools/build_roster.py    -> nfl-data.js  (needs only files committed under tools/)

Rules enforced here:
  * every card is a real player-season on that franchise's roster (lineage-mapped),
  * the season year is inside the dial decade,
  * the player held that position group that season (OT / OG / C and DE / DT never mix,
    WR / TE never mix; K / P / RET come from that season's kicking / punting / return stats),
  * 3 distinct players per key, ranked the way a fan would: honours, years as a starter,
    production at that position for that team in that decade,
  * stats strings are copied from source tables (no invented numbers).
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from historical_seasons import HSEASONS  # noqa: E402
from depth_pad import DEPTH_PAD  # noqa: E402
from curated_fixes import FORCE_EXCLUDE, POS_OVERRIDE  # noqa: E402

SEASONS = HERE / "data" / "player_seasons.json.gz"
META = HERE / "data" / "meta.json"
OUT_JS = ROOT / "nfl-data.js"
REPORT = HERE / "data" / "build_report.json"

DECADES = ["1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"]
OFFENSE_TWO_BACK = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "LT", "LG", "C", "RG", "RT"]
OFFENSE_SINGLE_BACK = ["QB", "RB", "WR1", "WR2", "WR3", "TE", "LT", "LG", "C", "RG", "RT"]
DEFENSE_43 = ["LDE", "LDT", "RDT", "RDE", "WLB", "MLB", "SLB", "LCB", "RCB", "SS", "FS"]
DEFENSE_34 = ["LE", "NT", "RE", "LOLB", "LILB", "RILB", "ROLB", "LCB", "RCB", "SS", "FS"]
SPECIAL = ["K", "P", "RET"]
SLOTS = list(dict.fromkeys(OFFENSE_TWO_BACK + OFFENSE_SINGLE_BACK + DEFENSE_43 + DEFENSE_34 + SPECIAL))

TEAMS = [
    ("ARI", "Arizona Cardinals"), ("ATL", "Atlanta Falcons"), ("BAL", "Baltimore Ravens"),
    ("BUF", "Buffalo Bills"), ("CAR", "Carolina Panthers"), ("CHI", "Chicago Bears"),
    ("CIN", "Cincinnati Bengals"), ("CLE", "Cleveland Browns"), ("DAL", "Dallas Cowboys"),
    ("DEN", "Denver Broncos"), ("DET", "Detroit Lions"), ("GB", "Green Bay Packers"),
    ("HOU", "Houston Texans"), ("IND", "Indianapolis Colts"), ("JAX", "Jacksonville Jaguars"),
    ("KC", "Kansas City Chiefs"), ("LAC", "Los Angeles Chargers"), ("LAR", "Los Angeles Rams"),
    ("LV", "Las Vegas Raiders"), ("MIA", "Miami Dolphins"), ("MIN", "Minnesota Vikings"),
    ("NE", "New England Patriots"), ("NO", "New Orleans Saints"), ("NYG", "New York Giants"),
    ("NYJ", "New York Jets"), ("PHI", "Philadelphia Eagles"), ("PIT", "Pittsburgh Steelers"),
    ("SEA", "Seattle Seahawks"), ("SF", "San Francisco 49ers"), ("TB", "Tampa Bay Buccaneers"),
    ("TEN", "Tennessee Titans"), ("WAS", "Washington Commanders"),
]
TEAM_CODES = [t[0] for t in TEAMS]
# First season of the modern franchise (AFL years count; predecessors folded in).
FOUNDING = {
    "ARI": 1920, "ATL": 1966, "BAL": 1996, "BUF": 1960, "CAR": 1995, "CHI": 1920,
    "CIN": 1968, "CLE": 1946, "DAL": 1960, "DEN": 1960, "DET": 1930, "GB": 1919,
    "HOU": 2002, "IND": 1953, "JAX": 1995, "KC": 1960, "LAC": 1960, "LAR": 1936,
    "LV": 1960, "MIA": 1966, "MIN": 1961, "NE": 1960, "NO": 1967, "NYG": 1925,
    "NYJ": 1960, "PHI": 1933, "PIT": 1933, "SEA": 1976, "SF": 1946, "TB": 1976,
    "TEN": 1960, "WAS": 1932,
}
# Seasons a franchise did not play (Browns suspended 1996-98).
GAPS = {"CLE": set(range(1996, 1999))}

# Historical name a fan would use for the franchise in a given year (for blurbs).
def era_name(team: str, year: int) -> str:
    if team == "NYJ" and year <= 1962: return "Titans of New York"
    if team == "NE" and year <= 1970: return "Boston Patriots"
    if team == "KC" and year <= 1962: return "Dallas Texans"
    if team == "LAC": return "Los Angeles Chargers" if (year == 1960 or year >= 2017) else "San Diego Chargers"
    if team == "TEN": return "Houston Oilers" if year <= 1996 else "Tennessee Oilers" if year <= 1998 else "Tennessee Titans"
    if team == "IND": return "Baltimore Colts" if year <= 1983 else "Indianapolis Colts"
    if team == "ARI": return "St. Louis Cardinals" if year <= 1987 else "Phoenix Cardinals" if year <= 1993 else "Arizona Cardinals"
    if team == "LAR": return "St. Louis Rams" if 1995 <= year <= 2015 else "Los Angeles Rams"
    if team == "LV": return "Los Angeles Raiders" if 1982 <= year <= 1994 else "Oakland Raiders" if year <= 2019 else "Las Vegas Raiders"
    if team == "WAS": return "Washington Redskins" if year <= 2019 else "Washington Football Team" if year <= 2021 else "Washington Commanders"
    return dict(TEAMS)[team]


NICK = {c: n.split()[-1] for c, n in TEAMS}
NICK["WAS"] = "Washington"

# ---------------------------------------------------------------- slot -> position groups
SLOT_GROUP = {
    "QB": ["QB"], "RB": ["RB"], "RB1": ["RB"], "RB2": ["RB"],
    "WR1": ["WR"], "WR2": ["WR"], "WR3": ["WR"], "TE": ["TE"],
    "LT": ["OT"], "RT": ["OT"], "LG": ["OG"], "RG": ["OG"], "C": ["C"],
    "LDE": ["DE"], "RDE": ["DE"], "LE": ["DE"], "RE": ["DE"],
    "LDT": ["DT"], "RDT": ["DT"], "NT": ["DT"],
    "WLB": ["OLB", "LB"], "SLB": ["OLB", "LB"], "LOLB": ["OLB", "LB"], "ROLB": ["OLB", "LB"],
    "MLB": ["MLB", "LB"], "LILB": ["MLB", "LB"], "RILB": ["MLB", "LB"],
    "LCB": ["CB"], "RCB": ["CB"], "SS": ["SS", "S"], "FS": ["FS", "S"],
    "K": ["K"], "P": ["P"], "RET": ["RET"],
}
# Last-resort widening, same family only (never OL<->OL, DL<->DL, skill<->skill, CB<->S).
LAST_RESORT = {"OLB": ["MLB"], "MLB": ["OLB"], "SS": ["FS"], "FS": ["SS"]}
# Rating families (tier distribution is calibrated per family).
FAMILY = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "OT": "OL", "OG": "OL", "C": "OL",
          "DE": "DL", "DT": "DL", "OLB": "LB", "MLB": "LB", "LB": "LB", "CB": "DB", "S": "DB", "SS": "DB",
          "FS": "DB", "K": "K", "P": "P", "RET": "RET"}
POS_LABEL = {"OT": "OT", "OG": "G", "C": "C"}


def season_games(year: int, lg: str = "nfl") -> int:
    if year == 1960 and lg == "nfl": return 12
    if year <= 1977: return 14
    if year == 1982: return 9
    if year == 1987: return 15
    if year <= 2020: return 16
    return 17


def era(year: int) -> str:
    return "a" if year < 1982 else "b" if year < 1999 else "c"


def decade_of(year: int) -> str:
    return f"{year // 10 * 10}s"


def team_years(team: str, dec: str) -> list[int]:
    s = int(dec[:4])
    return [y for y in range(s, s + 10) if y >= FOUNDING[team] and y not in GAPS.get(team, set()) and y <= 2025]


def norm(name: str) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", " ", n.replace(".", " ").replace("'", "").replace("-", " "))
    parts, out, buf = re.sub(r"[^a-z ]", " ", n).split(), [], ""
    for p in parts:
        if len(p) == 1:
            buf += p
            continue
        if buf:
            out.append(buf); buf = ""
        out.append(p)
    if buf:
        out.append(buf)
    return " ".join(out)


# ---------------------------------------------------------------- per-season value
def g_(st, k):
    return float(st.get(k, 0) or 0)


def avail(r):
    """Starts if known, else games; None when the source has neither (AFL footballdb pages)."""
    if r.get("gs") is not None:
        return float(r["gs"])
    if r.get("g"):
        return float(r["g"]) * 0.6
    return None


def raw_value(r, grp):
    st = r.get("st", {})
    L = season_games(r["year"], r.get("lg", "nfl"))
    sc = 16.0 / L
    a = avail(r)
    av = (a or 0.0) * sc
    if grp == "QB":
        return sc * (g_(st, "pa_yds") / 45 + g_(st, "pa_td") * 4.2 - g_(st, "pa_int") * 1.8 + g_(st, "ru_yds") / 80 + g_(st, "ru_td") * 2)
    if grp == "RB":
        return sc * (g_(st, "ru_yds") / 18 + g_(st, "rec_yds") / 28 + g_(st, "ru_td") * 5 + g_(st, "rec_td") * 4 + g_(st, "rec") * 0.4)
    if grp in ("WR", "TE"):
        return sc * (g_(st, "rec_yds") / 16 + g_(st, "rec") * 0.55 + g_(st, "rec_td") * 5 + g_(st, "ru_yds") / 40)
    if grp in ("DE", "DT", "OLB", "MLB", "LB"):
        return sc * (g_(st, "d_sack") * 9 + g_(st, "d_int") * 8 + g_(st, "d_tkl") * 0.35 + g_(st, "d_tfl") * 1.6 + g_(st, "d_ff") * 3) + av * 1.2
    if grp in ("CB", "S", "SS", "FS"):
        return sc * (g_(st, "d_int") * 12 + g_(st, "d_pd") * 2.2 + g_(st, "d_tkl") * 0.3 + g_(st, "d_sack") * 6 + g_(st, "d_ff") * 3) + av * 1.2
    if grp == "K":
        fgm, fga = g_(st, "fgm"), g_(st, "fga")
        pct = 100 * fgm / fga if fga else 0
        return sc * (fgm * 3.2 + g_(st, "xpm") * 0.35) + max(pct - 55, 0) * 0.6
    if grp == "P":
        n = g_(st, "punts")
        avg = g_(st, "punt_yds") / n if n and g_(st, "punt_yds") else g_(st, "punt_avg")
        return avg * 2.1 + n * sc * 0.05
    if grp == "RET":
        return sc * (g_(st, "kr_yds") / 18 + g_(st, "pr_yds") / 10 + (g_(st, "kr_td") + g_(st, "pr_td") + g_(st, "st_td")) * 18)
    # OL
    return av


def qualifies(r, grp):
    st = r.get("st", {})
    L = season_games(r["year"], r.get("lg", "nfl"))
    if grp == "K":
        return g_(st, "fga") >= 4 or g_(st, "xpa") >= 8
    if grp == "P":
        return g_(st, "punts") >= 12
    if grp == "RET":
        return g_(st, "kr") + g_(st, "pr") >= 8
    if grp == "QB":
        return g_(st, "pa_att") >= 40 or (r.get("gs") or 0) >= 2
    if grp == "RB":
        return g_(st, "ru_att") >= 15 or g_(st, "rec") >= 10 or (r.get("gs") or 0) >= 3
    if grp in ("WR", "TE"):
        return g_(st, "rec") >= 5 or (r.get("gs") or 0) >= 3
    # trench / defense: on the field
    if r.get("gs") is not None:
        return r["gs"] >= 1 or (r.get("g") or 0) >= L * 0.5
    if r.get("g"):
        return r["g"] >= max(4, L * 0.35)
    return True  # AFL rows (no G on source page) — roster presence only


def honor_bonus(r):
    ap, pb = r.get("ap"), r.get("pb")
    b = 0.0
    if ap == 1: b = 0.65
    elif ap == 2: b = 0.42
    if pb: b = max(b, 0.32) + (0.08 if b > 0.32 else 0)
    return b


def honor_text(r):
    bits = []
    if r.get("ap") == 1: bits.append("1st-team All-Pro" if r["year"] >= 1970 or r.get("lg") != "afl" else "1st-team All-AFL")
    elif r.get("ap") == 2: bits.append("2nd-team All-Pro" if r["year"] >= 1970 or r.get("lg") != "afl" else "2nd-team All-AFL")
    if r.get("pb"): bits.append("Pro Bowl" if r["year"] >= 1970 or r.get("lg") != "afl" else "AFL All-Star")
    return " · ".join(bits)


def fmt_num(x):
    x = float(x)
    if x == int(x):
        return f"{int(x):,}"
    return f"{x:.1f}"


def stat_line(r, grp):
    st = r.get("st", {})
    G, GS = r.get("g"), r.get("gs")
    games = ""
    if G:
        games = f"{G} G" + (f" · {GS} GS" if GS is not None else "")
    if grp == "QB":
        s = f"{fmt_num(g_(st,'pa_yds'))} yds · {int(g_(st,'pa_td'))} TD · {int(g_(st,'pa_int'))} INT"
        if g_(st, "ru_yds") >= 300: s += f" · {fmt_num(g_(st,'ru_yds'))} rush"
        return s
    if grp == "RB":
        s = f"{fmt_num(g_(st,'ru_yds'))} rush"
        if g_(st, "rec") >= 15: s += f" · {int(g_(st,'rec'))} rec · {fmt_num(g_(st,'rec_yds'))} yds"
        return s + f" · {int(g_(st,'ru_td') + g_(st,'rec_td'))} TD"
    if grp in ("WR", "TE"):
        s = f"{int(g_(st,'rec'))} rec · {fmt_num(g_(st,'rec_yds'))} yds · {int(g_(st,'rec_td'))} TD"
        if g_(st, "ru_yds") >= 80: s += f" · {fmt_num(g_(st,'ru_yds'))} rush"
        return s
    if grp == "K":
        s = f"{int(g_(st,'fgm'))}/{int(g_(st,'fga'))} FG"
        if g_(st, "xpa"): s += f" · {int(g_(st,'xpm'))}/{int(g_(st,'xpa'))} XP"
        elif g_(st, "xpm"): s += f" · {int(g_(st,'xpm'))} XP"
        return s
    if grp == "P":
        n = g_(st, "punts")
        avg = g_(st, "punt_yds") / n if n and g_(st, "punt_yds") else g_(st, "punt_avg")
        return f"{int(n)} punts · {avg:.1f} avg" if avg else f"{int(n)} punts"
    if grp == "RET":
        bits = []
        if g_(st, "kr"): bits.append(f"{int(g_(st,'kr'))} KR · {g_(st,'kr_yds')/g_(st,'kr'):.1f} avg")
        if g_(st, "pr"): bits.append(f"{int(g_(st,'pr'))} PR · {g_(st,'pr_yds')/g_(st,'pr'):.1f} avg")
        td = g_(st, "kr_td") + g_(st, "pr_td") + g_(st, "st_td")
        if td: bits.append(f"{int(td)} TD")
        return " · ".join(bits)
    bits = []
    if grp in ("DE", "DT", "OLB", "MLB", "LB", "CB", "S", "SS", "FS"):
        if g_(st, "d_sack"): bits.append(f"{fmt_num(g_(st,'d_sack'))} sacks")
        if g_(st, "d_tkl"): bits.append(f"{int(g_(st,'d_tkl'))} tkl")
        if g_(st, "d_int"): bits.append(f"{int(g_(st,'d_int'))} INT")
        if g_(st, "d_pd") and grp in ("CB", "S", "SS", "FS"): bits.append(f"{int(g_(st,'d_pd'))} PD")
    if games:
        bits.append(games)
    return " · ".join(bits)


# ---------------------------------------------------------------- load
def load_seasons():
    rows = json.load(gzip.open(SEASONS, "rt", encoding="utf-8"))
    out = []
    for r in rows:
        if r["team"] not in TEAM_CODES:
            continue
        if r["year"] < FOUNDING[r["team"]] or r["year"] in GAPS.get(r["team"], set()):
            continue
        key = (r["id"], r["team"], r["year"])
        if key in FORCE_EXCLUDE:
            continue
        if key in POS_OVERRIDE:
            r["pos"] = POS_OVERRIDE[key]
        r.setdefault("st", {})
        out.append(r)
    return out


def curated_index():
    idx = defaultdict(list)
    for row in list(HSEASONS) + list(DEPTH_PAD):
        name, team, pos, year, jersey, rating, tier, stats, blurb = row
        idx[(norm(name), team, int(year))].append({"pos": pos, "jersey": jersey, "blurb": blurb, "stats": stats})
    return idx


CUR_COMPAT = {"LB": {"OLB", "MLB", "LB"}, "S": {"S", "SS", "FS"}, "CB": {"CB"}, "OLB": {"OLB", "LB"},
              "MLB": {"MLB", "LB"}, "OT": {"OT"}, "OG": {"OG"}, "C": {"C"}, "DE": {"DE"}, "DT": {"DT"}}


def main():
    seasons = load_seasons()
    cur = curated_index()
    meta = json.loads(META.read_text())
    print("player-seasons", len(seasons))

    # Jersey consistency per (player, team) for seasons where the source page lacks it.
    jerseys = defaultdict(dict)
    for r in seasons:
        if r.get("jersey") is not None:
            jerseys[(r["id"], r["team"])][r["year"]] = r["jersey"]
    def jersey_for(r):
        if r.get("jersey") is not None:
            return r["jersey"]
        known = jerseys.get((r["id"], r["team"]), {})
        if known and len(set(known.values())) == 1 and min(abs(y - r["year"]) for y in known) <= 3:
            return next(iter(known.values()))
        for c in cur.get((norm(r["name"]), r["team"], r["year"]), []):
            if c["jersey"] is not None:
                return c["jersey"]
        return None

    # ---- expand into (group, season) entries
    entries = []  # dict(rec, grp)
    depth_entries = []
    for r in seasons:
        p = r.get("pos")
        grps = []
        if p in FAMILY and p not in ("K", "P", "RET"):
            grps.append(p)
        st = r["st"]
        if qualifies(r, "K"): grps.append("K")
        if qualifies(r, "P"): grps.append("P")
        if qualifies(r, "RET"): grps.append("RET")
        if p in ("K", "P") and p not in grps and (r.get("g") or 0) >= 1 and not st:
            pass  # kicker on roster but no kicks recorded -> not a K season
        for gp in grps:
            if gp in ("K", "P", "RET") or qualifies(r, gp):
                entries.append({"r": r, "grp": gp})
            else:
                depth_entries.append({"r": r, "grp": gp, "depth": True})
        # Depth-only seasons (real roster seasons below the "qualified" bar): used only when a
        # team-decade has fewer than 3 qualified players at a spot (e.g. one kicker all decade).
        if p in ("K", "P") and p not in grps and (r.get("g") or st):
            depth_entries.append({"r": r, "grp": p, "depth": True})
        # occasional kickers / punters (e.g. a position player who punted when the punter was hurt)
        if "K" not in grps and p != "K" and g_(st, "fga") + g_(st, "xpa") + g_(st, "fgm") + g_(st, "xpm") >= 1:
            depth_entries.append({"r": r, "grp": "K", "depth": True})
        if "P" not in grps and p != "P" and g_(st, "punts") >= 1:
            depth_entries.append({"r": r, "grp": "P", "depth": True})
        if "RET" not in grps and g_(st, "kr") + g_(st, "pr") >= 1:
            depth_entries.append({"r": r, "grp": "RET", "depth": True})
    print("position-season entries", len(entries), "depth-only", len(depth_entries))

    # ---- percentile of raw value within (group, era) among qualified seasons
    pools = defaultdict(list)
    for e in entries:
        e["raw"] = raw_value(e["r"], e["grp"])
        e["has_avail"] = avail(e["r"]) is not None
        pools[(e["grp"], era(e["r"]["year"]), e["has_avail"] or e["grp"] in ("QB", "RB", "WR", "TE", "K", "P", "RET"))].append(e["raw"])
    for k in pools:
        pools[k].sort()
    import bisect
    for e in entries:
        pool = pools[(e["grp"], era(e["r"]["year"]), e["has_avail"] or e["grp"] in ("QB", "RB", "WR", "TE", "K", "P", "RET"))]
        if e["grp"] in ("OT", "OG", "C", "DE", "DT", "OLB", "MLB", "LB", "CB", "S", "SS", "FS") and not e["has_avail"] and not e["r"]["st"]:
            pct = 0.5  # AFL trench row with no games / stats on the source page: neutral
        else:
            lo = bisect.bisect_left(pool, e["raw"]); hi = bisect.bisect_right(pool, e["raw"])
            pct = ((lo + hi) / 2) / max(1, len(pool))
        e["pct"] = pct
        e["score"] = pct + honor_bonus(e["r"])
    for e in depth_entries:
        e["raw"] = raw_value(e["r"], e["grp"])
        e["has_avail"] = avail(e["r"]) is not None
        pool = pools.get((e["grp"], era(e["r"]["year"]), e["has_avail"] or e["grp"] in ("QB", "RB", "WR", "TE", "K", "P", "RET")), [])
        e["pct"] = 0.5 * bisect.bisect_left(pool, e["raw"]) / max(1, len(pool))
        e["score"] = e["pct"] + honor_bonus(e["r"])

    # ---- career context per (player, team, family)
    career = defaultdict(lambda: {"pb": 0, "ap1": 0, "starts": 0, "years": set()})
    for e in entries:
        r = e["r"]
        c = career[(r["id"], r["team"], FAMILY[e["grp"]])]
        if r["year"] in c["years"]:
            continue
        c["years"].add(r["year"])
        c["pb"] += 1 if r.get("pb") else 0
        c["ap1"] += 1 if r.get("ap") == 1 else 0
        L = season_games(r["year"], r.get("lg", "nfl"))
        a = r.get("gs") if r.get("gs") is not None else (r.get("g") or 0) * 0.75 if r.get("g") else None
        if a is not None and a >= L * 0.5:
            c["starts"] += 1

    # ---- group by key bucket
    bucket = defaultdict(list)
    for e in entries:
        r = e["r"]
        bucket[(r["team"], decade_of(r["year"]), e["grp"])].append(e)
    dbucket = defaultdict(list)
    for e in depth_entries:
        r = e["r"]
        dbucket[(r["team"], decade_of(r["year"]), e["grp"])].append(e)

    def decade_rank(team, dec, grps, src=None):
        """Fan ranking: sum of season scores at this spot + honours/longevity bonuses."""
        src = bucket if src is None else src
        per = defaultdict(list)
        for gp in grps:
            for e in src.get((team, dec, gp), []):
                per[e["r"]["id"]].append(e)
        ranked = []
        for pid, es in per.items():
            # one entry per season (a player can be both S and SS in data — keep best)
            best_by_year = {}
            for e in es:
                y = e["r"]["year"]
                if y not in best_by_year or e["score"] > best_by_year[y]["score"]:
                    best_by_year[y] = e
            es = list(best_by_year.values())
            r0 = es[0]["r"]
            # diminishing returns on longevity so a 3-year star beats a 5-year journeyman
            sc = sorted((e["score"] for e in es), reverse=True)
            wts = [1.0, 0.8, 0.65, 0.5, 0.4]
            tot = sum(x * (wts[i] if i < len(wts) else 0.3) for i, x in enumerate(sc))
            starts = sum(1 for e in es if e["pct"] >= 0.55)
            v = tot + 0.12 * min(starts, 6)
            # franchise-career prestige at this position family (honours in any decade with this team)
            fam = FAMILY[es[0]["grp"]]
            car = career.get((r0["id"], team, fam))
            if car:
                v += 0.14 * min(car["pb"], 8) + 0.18 * min(car["ap1"], 5)
            if any(e["r"].get("hof") for e in es) and len(es) >= 2:
                v += 0.9
            if dec in (r0.get("alldec") or []):
                v += 0.6
            if any(cur.get((norm(e["r"]["name"]), team, e["r"]["year"])) for e in es):
                v += 0.15
            best = max(es, key=lambda e: (e["score"], e["raw"], -abs(e["r"]["year"] - 0)))
            ranked.append((v, best, es))
        ranked.sort(key=lambda t: (-t[0], -t[1]["score"], t[1]["r"]["name"]))
        return ranked

    roster, shortfalls, widened, depth_used = {}, [], [], []
    picked_cards = []
    for team, _ in TEAMS:
        for dec in DECADES:
            years = team_years(team, dec)
            for slot in SLOTS:
                key = f"{team}|{dec}|{slot}"
                if not years:
                    roster[key] = []
                    continue
                grps = SLOT_GROUP[slot]
                ranked = decade_rank(team, dec, grps)
                if os.environ.get("DEBUG_KEY") == key:
                    for v, b, es in ranked[:8]:
                        print("DEBUG", key, b["r"]["name"], round(v, 2), [(e["r"]["year"], round(e["score"], 2)) for e in es])
                chosen = ranked[:3]
                if len(chosen) < 3:
                    # same position, real roster seasons below the qualified bar (backups)
                    have = {c[1]["r"]["id"] for c in chosen}
                    for x in decade_rank(team, dec, grps, dbucket):
                        if len(chosen) >= 3:
                            break
                        if x[1]["r"]["id"] not in have:
                            chosen.append(x)
                            have.add(x[1]["r"]["id"])
                            depth_used.append((key, x[1]["r"]["name"]))
                if len(chosen) < 3:
                    extra = []
                    for g0 in grps:
                        extra += LAST_RESORT.get(g0, [])
                    if extra:
                        have = {c[1]["r"]["id"] for c in chosen}
                        more = [x for x in decade_rank(team, dec, extra) if x[1]["r"]["id"] not in have]
                        for x in more[: 3 - len(chosen)]:
                            widened.append((key, x[1]["r"]["name"], x[1]["grp"]))
                            chosen.append(x)
                if len(chosen) < 3:
                    shortfalls.append((key, [c[1]["r"]["name"] for c in chosen]))
                cards = []
                for v, best, es in chosen[:3]:
                    cards.append({"v": v, "best": best, "es": es, "slot": slot, "key": key})
                    picked_cards.append(cards[-1])
                roster[key] = cards

    # ---- ratings: raw card strength, then per-family calibration to a common tier mix
    def card_raw(c):
        b, r, fam = c["best"], c["best"]["r"], FAMILY[c["best"]["grp"]]
        car = career[(r["id"], r["team"], fam)]
        base = b["score"]
        if fam == "OL":
            # OL: availability percentile is weak on its own -> weight honours, HOF, starts, longevity.
            base = 0.35 * b["pct"] + honor_bonus(r) + 0.07 * min(car["pb"], 8) + 0.12 * min(car["ap1"], 4) \
                + (0.45 if r.get("hof") else 0) + 0.045 * min(car["starts"], 12)
        else:
            base += 0.035 * min(car["pb"], 8) + 0.05 * min(car["ap1"], 4) + (0.3 if r.get("hof") else 0) + 0.02 * min(car["starts"], 10)
        return base

    TARGET = [(0.25, 72, 83), (0.65, 84, 91), (1.0, 92, 99)]  # Starter 25%, Star 40%, Legend 35%
    fam_cards = defaultdict(list)
    uniq = {}
    for c in picked_cards:
        k = (c["best"]["r"]["id"], c["best"]["r"]["team"], c["best"]["r"]["year"], c["best"]["grp"])
        uniq.setdefault(k, []).append(c)
    for k, cs in uniq.items():
        fam_cards[FAMILY[k[3]]].append((card_raw(cs[0]), k))
    rating_of = {}
    for fam, lst in fam_cards.items():
        lst.sort()
        n = len(lst)
        for i, (raw, k) in enumerate(lst):
            q = (i + 0.5) / n
            lo_q = 0.0
            for hi_q, lo_r, hi_r in TARGET:
                if q <= hi_q:
                    rating = lo_r + (hi_r - lo_r) * (q - lo_q) / (hi_q - lo_q)
                    break
                lo_q = hi_q
            rating_of[k] = rating
    def finalize_rating(k, r):
        x = rating_of[k]
        if r.get("ap") == 1: x = max(x, 93)
        elif r.get("ap") == 2: x = max(x, 89)
        if r.get("pb"): x = max(x, 86)
        if r.get("hof"): x = max(x, 88)
        x = int(round(min(99, x)))
        tier = "Legend" if x >= 92 else "Star" if x >= 84 else "Starter"
        return x, tier

    # ---- cards
    report_cur = {"validated": 0, "unmatched": []}
    for key, cards in roster.items():
        team, dec, slot = key.split("|")
        out = []
        for c in cards:
            b = c["best"]; r = b["r"]; grp = b["grp"]
            k = (r["id"], r["team"], r["year"], grp)
            rating, tier = finalize_rating(k, r)
            yrs = sorted({e["r"]["year"] for e in c["es"]})
            span = f"{yrs[0]}" if len(yrs) == 1 else f"{yrs[0]}–{str(yrs[-1])[-2:]}" if yrs[0] // 100 == yrs[-1] // 100 else f"{yrs[0]}–{yrs[-1]}"
            label = {"OG": "G", "OLB": "OLB", "MLB": "LB" if False else "MLB"}.get(grp, grp)
            hon = honor_text(r)
            blurb_bits = []
            if hon: blurb_bits.append(f"{r['year']} {hon}")
            if r.get("hof"): blurb_bits.append("Hall of Famer")
            blurb_bits.append(f"{era_name(team, r['year'])} {label} {span}")
            curated = [x for x in cur.get((norm(r["name"]), team, r["year"]), [])]
            card = {
                "name": r["name"], "season": str(r["year"]), "pos": label,
                "rating": rating, "tier": tier,
                "stats": stat_line(r, grp) or (f"{r['g']} G" if r.get("g") else "")
                         or f"{len(yrs)} season{'s' if len(yrs) != 1 else ''} at {label} ({span})",
                "club": era_name(team, r["year"]),
                "blurb": " · ".join(blurb_bits),
                "generated": False, "jersey": jersey_for(r),
            }
            if curated:
                report_cur["validated"] += 1
            if r.get("photo"): card["photo"] = r["photo"]
            if r.get("wiki"): card["wiki"] = r["wiki"]
            out.append(card)
        out.sort(key=lambda c: -c["rating"])
        roster[key] = out

    # ---- sanity
    bad = []
    for key, cards in roster.items():
        team, dec, slot = key.split("|")
        s = int(dec[:4])
        names = [norm(c["name"]) for c in cards]
        if len(set(names)) != len(names): bad.append(("dup", key))
        for c in cards:
            if not (s <= int(c["season"]) <= s + 9): bad.append(("decade", key, c["name"]))
    print("sanity problems", len(bad), bad[:5])

    data = {
        "decades": DECADES,
        "teams": [{"code": c, "name": n} for c, n in TEAMS],
        "founding": FOUNDING,
        "gaps": {k: sorted(v) for k, v in GAPS.items()},
        "positions": SLOTS, "offense": OFFENSE_TWO_BACK, "defense": DEFENSE_43, "special": SPECIAL,
        "schemes": {"offense": {"twoBack": OFFENSE_TWO_BACK, "singleBack": OFFENSE_SINGLE_BACK},
                    "defense": {"fourThree": DEFENSE_43, "threeFour": DEFENSE_34}},
        "rosterDB": roster,
        "coaches": meta.get("coaches", {}), "champHeroes": meta.get("champHeroes", {}), "sbMvps": meta.get("sbMvps", {}),
    }
    OUT_JS.write_text("window.NFL_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("wrote", OUT_JS, OUT_JS.stat().st_size)
    print("shortfalls", len(shortfalls), "last-resort widened", len(widened), "depth-filled", len(depth_used))
    REPORT.write_text(json.dumps({"shortfalls": shortfalls, "widened": widened, "depth_filled": depth_used, "curated_validated": report_cur["validated"]}, indent=1))


if __name__ == "__main__":
    main()
