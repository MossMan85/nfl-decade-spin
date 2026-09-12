#!/usr/bin/env python3
"""Build a real-player rosterDB for NFL Decade Spin. Zero fictional names."""

from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from historical_seasons import HSEASONS

WIKI = Path("/tmp/nfldata/wiki")
STATS_DIR = Path("/tmp/nfldata/stats")
ROSTER_DIR = Path("/tmp/nfldata/rosters")
INDEX = ROOT / "index.html"
OUT_JS = ROOT / "nfl-data.js"

DECADES = ["1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"]
OFFENSE = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "LT", "LG", "C", "RG", "RT"]
DEFENSE = ["LDE", "LDT", "RDT", "RDE", "WLB", "MLB", "SLB", "LCB", "RCB", "SS", "FS"]
SPECIAL = ["K", "P", "RET"]
SLOTS = OFFENSE + DEFENSE + SPECIAL

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

# First NFL/AFL season for the modern franchise (predecessors included).
FOUNDING = {
    "ARI": 1920, "ATL": 1966, "BAL": 1996, "BUF": 1960, "CAR": 1995, "CHI": 1920,
    "CIN": 1968, "CLE": 1946, "DAL": 1960, "DEN": 1960, "DET": 1930, "GB": 1919,
    "HOU": 2002, "IND": 1953, "JAX": 1995, "KC": 1960, "LAC": 1960, "LAR": 1936,
    "LV": 1960, "MIA": 1966, "MIN": 1961, "NE": 1960, "NO": 1967, "NYG": 1925,
    "NYJ": 1960, "PHI": 1933, "PIT": 1933, "SEA": 1976, "SF": 1946, "TB": 1976,
    "TEN": 1960, "WAS": 1932,
}

# nflverse / historical abbreviations -> modern franchise.
NFLVERSE_TEAM = {
    "ARI": "ARI", "PHO": "ARI", "PHX": "ARI", "STL": None,  # year-aware
    "ATL": "ATL", "BAL": "BAL", "BUF": "BUF", "CAR": "CAR", "CHI": "CHI",
    "CIN": "CIN", "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET",
    "GB": "GB", "GNB": "GB", "HOU": None, "HST": "HOU", "IND": "IND",
    "JAX": "JAX", "JAC": "JAX", "KC": "KC", "KCC": "KC", "KAN": "KC",
    "LAC": "LAC", "SD": "LAC", "SDG": "LAC", "LAR": "LAR", "LA": None, "RAM": "LAR",
    "LV": "LV", "LVR": "LV", "OAK": "LV", "RAI": "LV", "MIA": "MIA",
    "MIN": "MIN", "NE": "NE", "NWE": "NE", "NO": "NO", "NOR": "NO",
    "NYG": "NYG", "NYJ": "NYJ", "PHI": "PHI", "PIT": "PIT",
    "SEA": "SEA", "SF": "SF", "SFO": "SF", "TB": "TB", "TAM": "TB",
    "TEN": "TEN", "OTI": "TEN", "WAS": "WAS", "WSH": "WAS",
}

FULL_TEAM = {
    "arizona cardinals": "ARI", "phoenix cardinals": "ARI", "st. louis cardinals": "ARI",
    "saint louis cardinals": "ARI", "chicago cardinals": "ARI",
    "atlanta falcons": "ATL", "baltimore ravens": "BAL", "buffalo bills": "BUF",
    "carolina panthers": "CAR", "chicago bears": "CHI", "cincinnati bengals": "CIN",
    "cleveland browns": "CLE", "dallas cowboys": "DAL", "denver broncos": "DEN",
    "detroit lions": "DET", "green bay packers": "GB", "houston texans": "HOU",
    "houston oilers": "TEN", "tennessee oilers": "TEN", "tennessee titans": "TEN",
    "indianapolis colts": "IND", "baltimore colts": "IND",
    "jacksonville jaguars": "JAX", "kansas city chiefs": "KC", "dallas texans": "KC",
    "los angeles chargers": "LAC", "san diego chargers": "LAC",
    "los angeles rams": "LAR", "st. louis rams": "LAR", "cleveland rams": "LAR",
    "las vegas raiders": "LV", "oakland raiders": "LV", "los angeles raiders": "LV",
    "miami dolphins": "MIA", "minnesota vikings": "MIN",
    "new england patriots": "NE", "boston patriots": "NE",
    "new orleans saints": "NO", "new york giants": "NYG", "new york jets": "NYJ",
    "new york titans": "NYJ", "philadelphia eagles": "PHI", "pittsburgh steelers": "PIT",
    "seattle seahawks": "SEA", "san francisco 49ers": "SF", "san francisco forty-niners": "SF",
    "tampa bay buccaneers": "TB",
    "washington commanders": "WAS", "washington football team": "WAS",
    "washington redskins": "WAS", "washington": "WAS",
}

SHORT_TEAM = {
    "cardinals": "ARI", "arizona": "ARI", "phoenix": "ARI",
    "falcons": "ATL", "atlanta": "ATL",
    "ravens": "BAL",
    "bills": "BUF", "buffalo": "BUF",
    "panthers": "CAR", "carolina": "CAR",
    "bears": "CHI", "chicago": "CHI",
    "bengals": "CIN", "cincinnati": "CIN",
    "browns": "CLE", "cleveland": "CLE",
    "cowboys": "DAL", "dallas": "DAL",
    "broncos": "DEN", "denver": "DEN",
    "lions": "DET", "detroit": "DET",
    "packers": "GB", "green bay": "GB",
    "texans": "HOU",
    "titans": "TEN", "oilers": "TEN",
    "colts": "IND",
    "jaguars": "JAX", "jags": "JAX", "jacksonville": "JAX",
    "chiefs": "KC", "kansas city": "KC",
    "chargers": "LAC", "san diego": "LAC",
    "rams": "LAR",
    "raiders": "LV", "oakland": "LV", "las vegas": "LV",
    "dolphins": "MIA", "miami": "MIA",
    "vikings": "MIN", "minnesota": "MIN",
    "patriots": "NE", "new england": "NE", "boston": "NE",
    "saints": "NO", "new orleans": "NO",
    "giants": "NYG", "n.y. giants": "NYG", "ny giants": "NYG",
    "jets": "NYJ", "n.y. jets": "NYJ", "ny jets": "NYJ", "titans of new york": "NYJ",
    "eagles": "PHI", "philadelphia": "PHI",
    "steelers": "PIT", "pittsburgh": "PIT",
    "seahawks": "SEA", "seattle": "SEA",
    "49ers": "SF", "niners": "SF", "san francisco": "SF",
    "buccaneers": "TB", "bucs": "TB", "tampa bay": "TB", "tampa": "TB",
    "redskins": "WAS", "commanders": "WAS", "washington": "WAS",
}

POS_HEAD = {
    "quarterback": "QB", "quarterbacks": "QB",
    "running back": "RB", "running backs": "RB", "halfback": "RB", "halfbacks": "RB",
    "fullback": "RB", "fullbacks": "RB", "tailback": "RB",
    "wide receiver": "WR", "wide receivers": "WR", "flanker": "WR", "flankers": "WR",
    "split end": "WR", "split ends": "WR",
    # Bare "end(s)" is ambiguous (SE vs TE historically) — skip; use tight end / WR labels.
    "tight end": "TE", "tight ends": "TE",
    "tackle": "OT", "tackles": "OT", "offensive tackle": "OT", "offensive tackles": "OT",
    "guard": "OG", "guards": "OG", "offensive guard": "OG", "offensive guards": "OG",
    "center": "C", "centers": "C",
    "defensive end": "DE", "defensive ends": "DE",
    "defensive tackle": "DT", "defensive tackles": "DT", "nose tackle": "DT",
    "middle guard": "DT", "middle guards": "DT",
    "linebacker": "LB", "linebackers": "LB",
    "outside linebacker": "OLB", "inside linebacker": "MLB", "middle linebacker": "MLB",
    "cornerback": "CB", "cornerbacks": "CB", "corner": "CB", "defensive back": "CB",
    "defensive backs": "CB", "halfback (defensive)": "CB",
    "safety": "S", "safeties": "S", "strong safety": "SS", "free safety": "FS",
    "kicker": "K", "kickers": "K", "placekicker": "K", "placekickers": "K",
    "punter": "P", "punters": "P",
    "kick returner": "RET", "punt returner": "RET", "returner": "RET",
    "return specialist": "RET", "return specialists": "RET",
    "special teams": "RET",
}

SLOT_GROUP = {
    "QB": ["QB"],
    "RB1": ["RB"], "RB2": ["RB"],
    "WR1": ["WR"], "WR2": ["WR"],
    "TE": ["TE"],
    "LT": ["OT"], "RT": ["OT"],
    "LG": ["OG"], "RG": ["OG"],
    "C": ["C"],
    "LDE": ["DE"], "RDE": ["DE"],
    "LDT": ["DT"], "RDT": ["DT"],
    "WLB": ["OLB", "LB"], "SLB": ["OLB", "LB"], "MLB": ["MLB", "LB"],
    "LCB": ["CB"], "RCB": ["CB"],
    "SS": ["SS", "S"], "FS": ["FS", "S"],
    "K": ["K"], "P": ["P"], "RET": ["RET"],
}

# OL/DL/LB/DB may widen within trench/secondary. Skill groups (QB/RB/WR/TE/K/P) never widen.
WIDEN = {
    "OT": ["OG", "C"], "OG": ["OT", "C"], "C": ["OG", "OT"],
    "DE": ["OLB", "DT"], "DT": ["DE"],
    "OLB": ["DE", "LB", "MLB"], "MLB": ["LB", "OLB"], "LB": ["OLB", "MLB"],
    "CB": ["S", "FS", "SS"], "S": ["CB", "FS", "SS"], "SS": ["S", "FS", "CB"], "FS": ["S", "SS", "CB"],
    # RET may borrow return-capable skill/DB bodies; do not widen WR/TE/QB/RB/K/P into each other.
    "RET": ["WR", "RB", "CB"],
}

SKILL_NO_WIDEN = {"QB", "RB", "WR", "TE", "K", "P"}

NFLVERSE_POS = {
    "QB": "QB",
    "RB": "RB", "FB": "RB", "HB": "RB",
    "WR": "WR",
    "TE": "TE",
    "T": "OT", "OT": "OT",
    "G": "OG", "OG": "OG",
    "C": "C",
    "OL": "OT",
    "DE": "DE", "LE": "DE", "RE": "DE",
    "DT": "DT", "NT": "DT",
    "DL": "DE",
    "LB": "LB", "ILB": "MLB", "MLB": "MLB", "OLB": "OLB", "WLB": "OLB", "SLB": "OLB",
    "CB": "CB", "DB": "CB",
    "S": "S", "SS": "SS", "FS": "FS", "SAF": "S",
    "K": "K", "PK": "K",
    "P": "P",
    "LS": None,
    "KR": "RET", "PR": "RET",
}


def decade_of(year: int) -> str:
    return f"{(year // 10) * 10}s"


def num(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def clean_name(name: str) -> str:
    name = html.unescape(name or "")
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\s+", " ", name).strip(" ,;.|")
    name = re.sub(r"\bO\.\s*J\.\s*", "O.J. ", name)
    name = re.sub(r"\bA\.\s*J\.\s*", "A.J. ", name)
    name = re.sub(r"\bT\.\s*J\.\s*", "T.J. ", name)
    name = re.sub(r"\bC\.\s*J\.\s*", "C.J. ", name)
    name = re.sub(r"\bJ\.\s*J\.\s*", "J.J. ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def name_key(name: str) -> str:
    n = clean_name(name).lower()
    n = n.replace(".", "").replace("'", "").replace("’", "")
    n = re.sub(r"\s+", " ", n).strip()
    # collapse "Joe Conrad" into "Bobby Joe Conrad" style suffixes later
    return n


ALIASES = {
    "joe conrad": "bobby joe conrad",
    "oj simpson": "oj simpson",
    "mean joe greene": "joe greene",
    "joe greene": "joe greene",
    "moose johnston": "daryl johnston",
    "daryl johnston": "daryl johnston",
}


def map_full_team(raw: str, year: int | None = None) -> str | None:
    t = re.sub(r"\s+", " ", (raw or "").strip(" ,;.")).lower()
    t = t.replace("football club", "").strip()
    if t in FULL_TEAM:
        code = FULL_TEAM[t]
        return code
    # year-aware ambiguous cities
    if t in ("st. louis", "saint louis"):
        if year and year >= 1995:
            return "LAR"
        return "ARI"
    if t in ("houston",):
        if year and year >= 2002:
            return "HOU"
        return "TEN"
    if t in ("baltimore",):
        if year and year >= 1996:
            return "BAL"
        return "IND"
    if t in ("los angeles", "l.a.", "la"):
        if year and 1982 <= year <= 1994:
            return "LV"  # often Raiders in Pro Bowl short labels; prefer full names
        return "LAR"
    if t in SHORT_TEAM:
        return SHORT_TEAM[t]
    # last token nick
    parts = t.replace(".", "").split()
    if parts and parts[-1] in SHORT_TEAM:
        return SHORT_TEAM[parts[-1]]
    return None


def map_nflverse_team(code: str, year: int) -> str | None:
    c = (code or "").upper()
    if c == "STL":
        return "LAR" if year >= 1995 else "ARI"
    if c == "HOU":
        return "HOU" if year >= 2002 else "TEN"
    if c == "BAL":
        return "BAL" if year >= 1996 else "IND"
    if c == "LA":
        if 1982 <= year <= 1994:
            return "LV"
        return "LAR"
    mapped = NFLVERSE_TEAM.get(c, c if c in TEAM_CODES else None)
    return mapped


def map_pos_label(label: str) -> str | None:
    lab = re.sub(r"\s+", " ", (label or "").strip().lower())
    lab = lab.replace("(s)", "").replace("offence", "offense")
    # Ambiguous historical "End(s)" — do not guess WR vs TE.
    if lab in ("end", "ends"):
        return None
    if lab in POS_HEAD:
        return POS_HEAD[lab]
    # Prefer longer keys first so "tight end" / "defensive end" beat shorter stems.
    for key, val in sorted(POS_HEAD.items(), key=lambda kv: -len(kv[0])):
        if lab.startswith(key):
            return val
    return None


def map_nflverse_pos(pos: str, group: str | None = None) -> str | None:
    p = (pos or "").upper()
    if p in NFLVERSE_POS:
        return NFLVERSE_POS[p]
    g = (group or "").upper()
    if g in NFLVERSE_POS:
        return NFLVERSE_POS[g]
    return None


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|tr|h[1-6]|li|div|dt|dd)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = raw.replace("\xa0", " ")
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n\s+", "\n", raw)
    return raw


def parse_honor_line(line: str, year: int, pos: str, source: str) -> list[dict]:
    out = []
    line = re.sub(r"\[edit\]", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    if not line or len(line) < 6:
        return out
    # "Name , Team (AP, NEA)" possibly repeated
    chunks = re.split(r"(?<=\))\s+", line)
    if len(chunks) == 1:
        chunks = re.split(r"(?<=[a-z])\s+(?=[A-Z][a-z]+\s+[A-Z])", line)
    for chunk in chunks:
        chunk = chunk.strip(" |;")
        if "," not in chunk:
            continue
        m = re.match(
            r"^(?:(\d{1,2})\s+)?([A-Z][\w.'’\-]+(?:\s+[A-Z][\w.'’\-]+){1,3})\s*,\s*(.+)$",
            chunk,
        )
        if not m:
            # try "Name, Team"
            m2 = re.match(r"^(.{3,40}?)\s*,\s*(.{3,40})$", chunk)
            if not m2:
                continue
            jersey, name, team_raw = None, m2.group(1), m2.group(2)
        else:
            jersey, name, team_raw = m.group(1), m.group(2), m.group(3)
        team_raw = re.sub(r"\s*\(.*$", "", team_raw).strip(" ,;")
        # drop leftover position words
        if map_pos_label(name):
            continue
        team = map_full_team(team_raw, year)
        if not team:
            continue
        name = clean_name(name)
        if len(name.split()) < 2:
            continue
        honors = chunk
        first = bool(re.search(r"\bAP\b(?!-2)", chunk)) or "1st" in chunk.lower() or source == "all-decade"
        second = bool(re.search(r"AP-2|2nd", chunk))
        if source == "all-decade":
            rating, tier, stats, blurb = 94, "Legend", f"{decade_of(year)} All-Decade", "NFL All-Decade Team"
        elif first and not second:
            rating, tier, stats, blurb = 92, "Legend", "1st-team All-Pro", f"{year} All-Pro"
        elif second:
            rating, tier, stats, blurb = 86, "Star", "2nd-team All-Pro", f"{year} All-Pro"
        elif source == "probowl":
            rating, tier, stats, blurb = 82, "Star", "Pro Bowl", f"{year} Pro Bowl"
        else:
            rating, tier, stats, blurb = 84, "Star", "All-Pro / Pro Bowl", f"{year} honors"
        rec = {
            "name": name,
            "team": team,
            "pos": pos,
            "year": year,
            "jersey": int(jersey) if jersey else None,
            "rating": rating,
            "tier": tier,
            "stats": stats,
            "blurb": blurb,
            "source": source,
        }
        out.append(rec)
    return out


def parse_allpro(path: Path, year: int) -> list[dict]:
    if not path.exists() or path.stat().st_size < 2000:
        return []
    text = html_to_text(path.read_text(errors="ignore"))
    recs = []
    pos = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        head = re.sub(r"\[edit\]", "", line).strip().rstrip(":")
        mapped = map_pos_label(head)
        # Ambiguous historical "Ends" mixed SE and TE — skip the section.
        if head.lower() in ("end", "ends") and len(head.split()) <= 4:
            pos = None
            continue
        if mapped and len(head.split()) <= 4:
            pos = mapped
            continue
        if not pos:
            continue
        if "team" == head.lower() or head.lower() in ("offense", "defense", "special teams"):
            continue
        recs.extend(parse_honor_line(line, year, pos, "allpro"))
    return recs


def parse_probowl(path: Path, year: int) -> list[dict]:
    if not path.exists() or path.stat().st_size < 2000:
        return []
    text = html_to_text(path.read_text(errors="ignore"))
    # Flatten newlines so "Tight end\n82 Name, Team" still matches.
    text = re.sub(r"\s+", " ", text)
    recs = []
    # Rows often: "Quarterback 14 Ken Stabler, Oakland 12 Bob Griese, Miami"
    pos_pat = (
        r"(Quarterbacks?|Running backs?|Fullbacks?|Halfbacks?|Wide receivers?|"
        r"Tight ends?|Tackles?|Guards?|Centers?|Defensive ends?|Defensive tackles?|"
        r"Linebackers?|Cornerbacks?|Safeties?|Kickers?|Punters?|Returners?|"
        r"Kick returners?|Punt returners?|Special teams)"
    )
    for m in re.finditer(pos_pat + r"(.{8,800}?)" + r"(?=(?:" + pos_pat + r")|$)", text, re.I):
        pos = map_pos_label(m.group(1))
        if not pos:
            continue
        tail = m.group(2)
        # jersey Name, Team
        for pm in re.finditer(
            r"(?:(\d{1,2})\s+)?([A-Z][\w.'’\-]+(?:\s+[A-Z][\w.'’\-]+)+)\s*,\s*"
            r"([A-Za-z][A-Za-z.' \-]+?)(?=(?:\s+\d{1,2}\s+[A-Z])|$)",
            tail,
        ):
            jersey, name, team_raw = pm.group(1), pm.group(2), pm.group(3)
            team_raw = team_raw.strip(" .;")
            if team_raw.lower() in ("starter", "reserve", "reserves", "nfc", "afc"):
                continue
            team = map_full_team(team_raw, year)
            if not team:
                continue
            name = clean_name(name)
            if len(name.split()) < 2:
                continue
            recs.append({
                "name": name,
                "team": team,
                "pos": pos,
                "year": year,
                "jersey": int(jersey) if jersey else None,
                "rating": 82,
                "tier": "Star",
                "stats": "Pro Bowl",
                "blurb": f"{year} Pro Bowl",
                "source": "probowl",
            })
    return recs


def parse_alldecade(path: Path, decade: str) -> list[dict]:
    if not path.exists():
        return []
    year = int(decade[:4]) + 5
    text = html_to_text(path.read_text(errors="ignore"))
    recs = []
    pos = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        head = re.sub(r"\[edit\]", "", line).strip().rstrip(":")
        mapped = map_pos_label(head)
        if head.lower() in ("end", "ends") and len(head.split()) <= 5:
            pos = None
            continue
        if mapped and len(line.split()) <= 5:
            pos = mapped
            continue
        if not pos:
            continue
        recs.extend(parse_honor_line(line, year, pos, "all-decade"))
    return recs


def load_wiki_records() -> list[dict]:
    recs = []
    for y in range(1960, 1999):
        recs.extend(parse_allpro(WIKI / f"allpro_{y}.html", y))
        recs.extend(parse_probowl(WIKI / f"probowl_{y}.html", y))
    for dec in ["1960s", "1970s", "1980s", "1990s"]:
        recs.extend(parse_alldecade(WIKI / f"decade_{dec}.html", dec))
    return recs


def load_curated() -> list[dict]:
    recs = []
    for row in HSEASONS:
        name, team, pos, year, jersey, rating, tier, stats, blurb = row
        recs.append({
            "name": clean_name(name),
            "team": team,
            "pos": pos,
            "year": int(year),
            "jersey": jersey,
            "rating": int(rating),
            "tier": tier,
            "stats": stats,
            "blurb": blurb,
            "score": int(rating) * 25,
            "source": "curated",
        })
    return recs


def load_existing_reals() -> list[dict]:
    p = Path("/tmp/nfldata/existing_reals.json")
    if not p.exists():
        return []
    recs = []
    for row in json.loads(p.read_text()):
        if row.get("generated"):
            continue
        name = row.get("name") or ""
        if "Emergency" in name:
            continue
        try:
            year = int(str(row.get("season"))[:4])
        except Exception:
            continue
        pos = row.get("pos") or ""
        group = SLOT_GROUP.get(pos, [pos])[0] if pos else None
        if not group:
            continue
        blurb = (row.get("blurb") or "").strip()
        if blurb.lower() in {"emergency", "pair", "prior", "rot", "depth", "fill", "depth chart fill"}:
            blurb = f"{year} season"
        recs.append({
            "name": name,
            "team": row.get("team"),
            "pos": group,
            "year": year,
            "jersey": None,
            "rating": int(row.get("rating") or 76),
            "tier": row.get("tier") or "Starter",
            "stats": None,
            "blurb": blurb or f"{year} season",
            "source": "legacy-real",
        })
    return recs


def score_nflverse(row: dict, pos: str) -> tuple[float, str]:
    py = num(row.get("passing_yards"))
    ptd = num(row.get("passing_tds"))
    pint = num(row.get("passing_interceptions"))
    ry = num(row.get("rushing_yards"))
    rtd = num(row.get("rushing_tds"))
    rec = num(row.get("receptions"))
    recy = num(row.get("receiving_yards"))
    rectd = num(row.get("receiving_tds"))
    sacks = num(row.get("def_sacks"))
    ints = num(row.get("def_interceptions"))
    tkl = num(row.get("def_tackles_solo")) + 0.5 * num(row.get("def_tackle_assists"))
    tfl = num(row.get("def_tackles_for_loss"))
    pd = num(row.get("def_pass_defended"))
    fgm = num(row.get("fg_made"))
    fga = num(row.get("fg_att"))
    xp = num(row.get("pat_made"))
    pnt = num(row.get("pt_att"))
    pnty = num(row.get("pt_yards"))
    in20 = num(row.get("pt_inside_20"))
    kr = num(row.get("kickoff_returns"))
    kry = num(row.get("kickoff_return_yards"))
    pr = num(row.get("punt_returns"))
    pry = num(row.get("punt_return_yards"))
    sttd = num(row.get("special_teams_tds"))

    if pos == "QB":
        score = py / 45 + ptd * 4.2 - pint * 1.8 + ry / 80 + rtd * 2
        stats = f"{int(py):,} yds · {int(ptd)} TD · {int(pint)} INT"
        if ry >= 400:
            stats += f" · {int(ry)} rush"
        return score, stats
    if pos == "RB":
        score = ry / 18 + recy / 28 + rtd * 5 + rectd * 4 + rec * 0.4
        stats = f"{int(ry):,} rush"
        if rec >= 15:
            stats += f" · {int(rec)} rec · {int(recy):,} yds"
        stats += f" · {int(rtd + rectd)} TD"
        return score, stats
    if pos in ("WR", "TE"):
        score = recy / 16 + rec * 0.55 + rectd * 5 + ry / 40
        extra = f" · {int(ry)} rush" if ry >= 80 else ""
        stats = f"{int(rec)} rec · {int(recy):,} yds · {int(rectd)} TD{extra}"
        return score, stats
    if pos in ("DE", "DT", "OLB", "MLB", "LB"):
        score = sacks * 9 + ints * 8 + tkl * 0.35 + tfl * 1.6
        bits = []
        if sacks:
            bits.append(f"{sacks:.1f} sack" if sacks % 1 else f"{int(sacks)} sack")
        if tkl:
            bits.append(f"{int(round(tkl))} tkl")
        if ints:
            bits.append(f"{int(ints)} INT")
        if tfl:
            bits.append(f"{int(tfl)} TFL")
        stats = " · ".join(bits) or f"{int(round(tkl))} tkl"
        return score, stats
    if pos in ("CB", "S", "SS", "FS"):
        score = ints * 12 + pd * 2.2 + tkl * 0.3 + sacks * 6
        bits = []
        if ints:
            bits.append(f"{int(ints)} INT")
        if pd:
            bits.append(f"{int(pd)} PD")
        if tkl:
            bits.append(f"{int(round(tkl))} tkl")
        if sacks:
            bits.append(f"{sacks:.1f} sack")
        stats = " · ".join(bits) or f"{int(round(tkl))} tkl"
        return score, stats
    if pos == "K":
        pct = (fgm / fga * 100) if fga else 0
        score = fgm * 3.2 + xp * 0.35 + max(pct - 70, 0) * 0.4
        stats = f"{int(fgm)}/{int(fga)} FG · {int(xp)} XP"
        return score, stats
    if pos == "P":
        avg = (pnty / pnt) if pnt else 0
        score = avg * 2.1 + in20 * 0.8 + pnt * 0.05
        stats = f"{avg:.1f} avg · {int(in20)} In20" if pnt else "Punter"
        return score, stats
    if pos == "RET":
        score = kry / 18 + pry / 10 + sttd * 18 + kr * 0.2 + pr * 0.4
        bits = []
        if kr:
            bits.append(f"{kry/kr:.1f} KR avg" if kr else "")
        if pr:
            bits.append(f"{pry/pr:.1f} PR avg")
        if sttd:
            bits.append(f"{int(sttd)} TD")
        stats = " · ".join(b for b in bits if b) or "Return specialist"
        return score, stats
    # OL / unknown
    games = num(row.get("games"))
    score = games
    stats = f"{int(games)} games" if games else "Starter"
    return score, stats


def rating_from_score(score: float, pos: str) -> tuple[int, str]:
    # Absolute-ish thresholds so peak seasons become Stars/Legends.
    if pos == "QB":
        if score >= 175: r = 99
        elif score >= 155: r = 96
        elif score >= 135: r = 93
        elif score >= 115: r = 88
        elif score >= 90: r = 82
        else: r = 74
    elif pos == "RB":
        if score >= 145: r = 98
        elif score >= 115: r = 94
        elif score >= 90: r = 88
        elif score >= 65: r = 82
        else: r = 74
    elif pos in ("WR", "TE"):
        if score >= 130: r = 97
        elif score >= 105: r = 93
        elif score >= 80: r = 87
        elif score >= 55: r = 81
        else: r = 74
    elif pos in ("DE", "DT", "OLB", "MLB", "LB"):
        if score >= 90: r = 96
        elif score >= 65: r = 90
        elif score >= 45: r = 84
        elif score >= 28: r = 78
        else: r = 73
    elif pos in ("CB", "S", "SS", "FS"):
        if score >= 70: r = 95
        elif score >= 48: r = 88
        elif score >= 30: r = 82
        else: r = 74
    elif pos == "K":
        if score >= 130: r = 94
        elif score >= 105: r = 88
        elif score >= 80: r = 82
        else: r = 74
    elif pos == "P":
        if score >= 115: r = 92
        elif score >= 100: r = 86
        elif score >= 85: r = 80
        else: r = 74
    elif pos == "RET":
        if score >= 90: r = 94
        elif score >= 60: r = 86
        elif score >= 35: r = 80
        else: r = 73
    else:
        if score >= 16: r = 82
        elif score >= 12: r = 78
        else: r = 74
    if r >= 92:
        tier = "Legend"
    elif r >= 84:
        tier = "Star"
    else:
        tier = "Starter"
    return r, tier


def load_nflverse() -> list[dict]:
    recs = []
    roster_jersey = {}
    roster_photo = {}
    roster_weeks = defaultdict(int)
    if ROSTER_DIR.exists():
        for y in range(1999, 2026):
            path = ROSTER_DIR / f"roster_{y}.csv"
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8", errors="ignore") as f:
                for row in csv.DictReader(f):
                    name = row.get("full_name") or row.get("football_name") or ""
                    team = map_nflverse_team(row.get("team") or "", y)
                    pos = map_nflverse_pos(row.get("position") or "", row.get("position_group"))
                    if not name or not team or not pos:
                        continue
                    key = (name, team, y)
                    j = row.get("jersey_number")
                    if j not in (None, "", "NA"):
                        try:
                            roster_jersey[key] = int(float(j))
                        except ValueError:
                            pass
                    photo = row.get("headshot_url") or ""
                    if photo.startswith("http"):
                        roster_photo[key] = photo
                    roster_weeks[key + (pos,)] += 1

    for y in range(1999, 2026):
        path = STATS_DIR / f"stats_player_reg_{y}.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                name = row.get("player_display_name") or row.get("player_name") or ""
                team = map_nflverse_team(row.get("recent_team") or "", y)
                pos = map_nflverse_pos(row.get("position") or "", row.get("position_group"))
                if not name or not team or not pos:
                    continue
                score, stats = score_nflverse(row, pos)
                # skip empty skill rows (true zeros on skill positions)
                if pos in ("QB", "RB", "WR", "TE") and score < 8:
                    continue
                if pos in ("K",) and num(row.get("fg_att")) < 8:
                    continue
                if pos in ("P",) and num(row.get("pt_att")) < 20:
                    continue
                if pos == "RET" and score < 12:
                    continue
                rating, tier = rating_from_score(score, pos)
                key = (name, team, y)
                recs.append({
                    "name": name,
                    "team": team,
                    "pos": pos,
                    "year": y,
                    "jersey": roster_jersey.get(key),
                    "rating": rating,
                    "tier": tier,
                    "stats": stats,
                    "blurb": f"{y} season",
                    "photo": row.get("headshot_url") or roster_photo.get(key),
                    "score": score,
                    "source": "nflverse",
                })

    # OL / depth from roster week counts (many OL have no box-score volume)
    for (name, team, year, pos), weeks in roster_weeks.items():
        if pos not in ("OT", "OG", "C", "DE", "DT", "OLB", "MLB", "LB"):
            continue
        if weeks < 8:
            continue
        key = (name, team, year)
        recs.append({
            "name": name,
            "team": team,
            "pos": pos,
            "year": year,
            "jersey": roster_jersey.get(key),
            "rating": 80 if weeks >= 16 else 76 if weeks >= 12 else 73,
            "tier": "Star" if weeks >= 16 else "Starter",
            "stats": f"{weeks} roster weeks",
            "blurb": f"{year} starter snaps",
            "photo": roster_photo.get(key),
            "score": weeks,
            "source": "roster",
        })
    return recs


def better(a: dict, b: dict) -> dict:
    """Merge two records for the same name/team/year/pos; keep richer stats + higher rating."""
    out = dict(b)
    if a.get("rating", 0) > out.get("rating", 0):
        out["rating"] = a["rating"]
        out["tier"] = a.get("tier", out.get("tier"))
    elif a.get("tier") == "Legend" and out.get("tier") != "Legend" and a.get("rating", 0) >= 90:
        out["tier"] = "Legend"
        out["rating"] = max(out.get("rating", 0), a["rating"])
    # Prefer counting-stat lines over honor-only
    def richness(s):
        s = s or ""
        return sum(ch.isdigit() for ch in s) + (8 if "yds" in s or "sack" in s or "FG" in s else 0)
    if richness(a.get("stats")) > richness(out.get("stats")):
        out["stats"] = a.get("stats")
        if a.get("blurb") and a.get("source") == "curated":
            out["blurb"] = a["blurb"]
    if a.get("source") == "curated" and a.get("blurb"):
        if out.get("blurb") in (None, "", f"{out.get('year')} season", f"{out.get('year')} Pro Bowl"):
            out["blurb"] = a["blurb"]
    if a.get("jersey") and not out.get("jersey"):
        out["jersey"] = a["jersey"]
    if a.get("photo") and not out.get("photo"):
        out["photo"] = a["photo"]
    # prefer curated blurb when ratings close
    if a.get("source") == "curated":
        out["blurb"] = a.get("blurb") or out.get("blurb")
        if a.get("stats") and richness(a.get("stats")) >= richness(out.get("stats")):
            out["stats"] = a["stats"]
    return out


def collapse_wr_te_conflicts(recs: list[dict]) -> list[dict]:
    """If the same player-team-year is tagged both WR and TE, keep one.

    Prefer curated/nflverse position, then TE when the other is honor-only WR,
    then the higher-rated / richer-stat row.
    """
    by = defaultdict(list)
    for r in recs:
        if r.get("pos") in ("WR", "TE"):
            nk = ALIASES.get(name_key(r["name"]), name_key(r["name"]))
            by[(nk, r["team"], r["year"])].append(r)
        else:
            by[("_other", id(r))].append(r)

    out = []
    seen_other = set()
    for key, rows in by.items():
        if key[0] == "_other":
            out.extend(rows)
            continue
        wrs = [r for r in rows if r["pos"] == "WR"]
        tes = [r for r in rows if r["pos"] == "TE"]
        if wrs and tes:
            def rank(r):
                src = {"curated": 3, "nflverse": 2, "roster": 2, "allpro": 1, "probowl": 1, "all-decade": 1}.get(r.get("source"), 0)
                rich = sum(ch.isdigit() for ch in (r.get("stats") or ""))
                return (src, r.get("rating", 0), rich)
            best_te = max(tes, key=rank)
            best_wr = max(wrs, key=rank)
            # Prefer curated/nflverse winner; tie-break toward TE when wiki honor-only WR.
            if rank(best_te) >= rank(best_wr):
                keep_pos = "TE"
            elif best_wr.get("source") in ("curated", "nflverse", "roster"):
                keep_pos = "WR"
            else:
                keep_pos = "TE"
            chosen = [r for r in rows if r["pos"] == keep_pos]
            # merge best of discarded pos honors into keeper via better()
            keep = chosen[0]
            for r in chosen[1:]:
                keep = better(keep, r)
            out.append(keep)
        else:
            out.extend(rows)
    return out


def merge_records(groups: list[list[dict]]) -> list[dict]:
    idx = {}
    order = []
    for bunch in groups:
        for r in bunch:
            if not r.get("name") or not r.get("team") or not r.get("pos"):
                continue
            if r["team"] not in TEAM_CODES:
                continue
            r["name"] = clean_name(r["name"])
            nk = ALIASES.get(name_key(r["name"]), name_key(r["name"]))
            if nk == "bobby joe conrad":
                r["name"] = "Bobby Joe Conrad"
            if nk == "daryl johnston":
                r["name"] = "Daryl Johnston"
            if nk == "joe greene":
                r["name"] = "Joe Greene"
            key = (nk, r["team"], r["year"], r["pos"])
            if key not in idx:
                idx[key] = r
                order.append(key)
            else:
                idx[key] = better(idx[key], r)
    return [idx[k] for k in order]


def pick_top(cands: list[dict], n: int = 3) -> list[dict]:
    # unique by name, best rating then year
    best = {}
    for r in cands:
        name = name_key(r["name"])
        prev = best.get(name)
        score = r.get("score", r.get("rating", 0) * 10)
        if not prev or (r.get("rating", 0), score, r.get("year", 0)) > (
            prev.get("rating", 0), prev.get("score", prev.get("rating", 0) * 10), prev.get("year", 0)
        ):
            best[name] = r
    ranked = sorted(best.values(), key=lambda r: (-r.get("rating", 0), -r.get("score", 0), -r.get("year", 0)))
    return ranked[:n]


def years_for_decade(dec: str) -> range:
    start = int(dec[:4])
    return range(start, start + 10)


def franchise_years(team: str, dec: str) -> list[int]:
    years = [y for y in years_for_decade(dec) if y >= FOUNDING[team]]
    if team == "CLE":
        years = [y for y in years if not (1996 <= y <= 1998)]
    return years


def collect_for(all_by: dict, team: str, dec: str, groups: list[str]) -> list[dict]:
    years = franchise_years(team, dec)
    out = []
    for g in groups:
        for y in years:
            out.extend(all_by.get((team, y, g), []))
    return out


def first_decade_for(team: str) -> str | None:
    """Earliest dial decade with any real franchise seasons."""
    for dec in DECADES:
        if franchise_years(team, dec):
            return dec
    return None


def fill_key(all_by: dict, team: str, dec: str, slot: str) -> list[dict]:
    """Fill a roster key with same-position players whose season year is IN `dec`.

    - Never widen WR/TE/QB/RB/K/P across skill groups.
    - Never pull neighbor-decade seasons into this decade's keys.
    - Pre-founding decades: borrow from the franchise's first real decade only
      (cards keep their real season years).
    """
    groups = SLOT_GROUP[slot]
    years = franchise_years(team, dec)

    # Expansion / pre-founding: use first decade the franchise existed.
    if not years:
        first = first_decade_for(team)
        if not first or first == dec:
            return []
        return fill_key(all_by, team, first, slot)

    cands = collect_for(all_by, team, dec, groups)
    picked = pick_top(cands, 3)
    if len(picked) >= 3:
        return picked

    # Widen only within OL/DL/LB/DB (and RET sources) — same decade only.
    primary = groups[0]
    extra_groups: list[str] = []
    if primary not in SKILL_NO_WIDEN:
        for g in groups:
            extra_groups.extend(WIDEN.get(g, []))
        extra_groups = [g for g in extra_groups if g not in groups]
        if extra_groups:
            cands = collect_for(all_by, team, dec, groups + extra_groups)
            picked = pick_top(cands, 3)

    # Prefer 1–2 real in-decade same-position players over wrong-pos / wrong-era fill.
    return pick_top(cands if cands else [], 3)


def to_card(rec: dict) -> dict:
    card = {
        "name": rec["name"],
        "season": str(rec["year"]),
        "rating": int(rec.get("rating") or 75),
        "tier": rec.get("tier") or "Starter",
        "blurb": rec.get("blurb") or f"{rec['year']} season",
        "stats": rec.get("stats") or rec.get("blurb") or f"{rec['year']} season",
        "generated": False,
    }
    if rec.get("jersey") not in (None, ""):
        card["jersey"] = int(rec["jersey"])
    photo = rec.get("photo")
    if photo and str(photo).startswith("http"):
        card["photo"] = photo
    return card


def load_meta():
    p = Path("/tmp/nfldata/meta.json")
    if p.exists():
        return json.loads(p.read_text())
    return None


def main():
    print("Loading curated…")
    curated = load_curated()
    print(" curated", len(curated))
    print("Loading wiki honors…")
    wiki = load_wiki_records()
    print(" wiki", len(wiki))
    print("Loading legacy reals…")
    legacy = load_existing_reals()
    print(" legacy", len(legacy))
    print("Loading nflverse…")
    modern = load_nflverse()
    print(" nflverse/roster", len(modern))

    merged = merge_records([curated, wiki, modern, legacy])
    merged = collapse_wr_te_conflicts(merged)
    print(" merged unique player-seasons", len(merged))

    all_by = defaultdict(list)
    for r in merged:
        all_by[(r["team"], r["year"], r["pos"])].append(r)

    roster = {}
    holes = []
    for team, _name in TEAMS:
        for dec in DECADES:
            for slot in SLOTS:
                picked = fill_key(all_by, team, dec, slot)
                key = f"{team}|{dec}|{slot}"
                if len(picked) < 3:
                    holes.append((key, [p["name"] for p in picked]))
                # Keep only real in-decade (or first-decade for pre-founding) cards —
                # never pad with wrong position or wrong-era seasons.
                roster[key] = [to_card(p) for p in picked[:3]]

    print("keys", len(roster), "expected", 32 * 7 * 25)
    print("holes after fallback", len(holes))
    if holes[:12]:
        print(" sample holes", holes[:12])

    # sanity: no emergency / obviously generated leftovers
    banned = {"Emergency Starter", "Keith Rowe", "Frank Caldwell", "Gene Cameron", "Don Drayton"}
    bad = []
    for key, players in roster.items():
        if len(players) < 3:
            bad.append(("short", key, [p["name"] for p in players]))
        for p in players:
            if p.get("generated") or any(b in p["name"] for b in banned):
                bad.append(("fake", key, p["name"]))
    print("bad flags", len(bad))

    meta = load_meta() or {}
    data = {
        "decades": DECADES,
        "teams": [{"code": c, "name": n} for c, n in TEAMS],
        "positions": SLOTS,
        "offense": OFFENSE,
        "defense": DEFENSE,
        "special": SPECIAL,
        "rosterDB": roster,
        "coaches": meta.get("coaches", {}),
        "champHeroes": meta.get("champHeroes", {}),
        "sbMvps": meta.get("sbMvps", {}),
    }

    js = "window.NFL_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT_JS.write_text(js)
    print("wrote", OUT_JS, "bytes", OUT_JS.stat().st_size)

    # coverage samples
    samples = [
        "CHI|1970s|RB1", "GB|1960s|QB", "BUF|1970s|RB1", "SF|1980s|WR1",
        "BAL|1960s|MLB", "HOU|1980s|DE", "JAX|1960s|LT", "CAR|1970s|K",
        "NE|2000s|QB", "KC|2010s|TE", "DET|1990s|RB1", "PIT|1970s|MLB",
        "SEA|2010s|CB", "TB|2000s|DT", "WAS|1980s|RB1", "LAC|1980s|QB",
        "ARI|1960s|WR1", "MIN|1970s|DE", "MIA|1970s|C", "LV|1970s|QB",
    ]
    for s in samples:
        names = [p["name"] + " " + p.get("stats", "") for p in roster.get(s, [])]
        print(s, "=>", names)

    # unique names + generated count
    names = {p["name"] for v in roster.values() for p in v}
    print("unique names in DB", len(names))
    print("DONE")


if __name__ == "__main__":
    main()
