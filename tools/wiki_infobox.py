#!/usr/bin/env python3
"""Slim Wikipedia infobox facts for pre-1975 players.

Input : raw infobox cache written by tools/fetch_sources.py (wiki-infobox step),
        default /tmp/nfldata/wiki_players/infobox_pre1975.json  {title: "{{Infobox ...}}"}
Output: tools/data/wiki_infobox.json
        {title: {"num": [jersey numbers], "afl_as": [season years], "pb": [season years], "pos": "..."}}

Only facts stated in the infobox are kept:
  * number    - jersey number(s) as listed (used by the builder only when exactly one number is listed)
  * AFL All-Star / Pro Bowl highlight lines - the displayed season years
  * position  - first listed position (used only to split generic "DB"/"LB" labels)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAWS = [Path(a) for a in sys.argv[1:]] or [Path("/tmp/nfldata/wiki_players/infobox_pre1975.json"),
                                        Path("/tmp/nfldata/wiki_players/afl_players.json")]
OUT = HERE / "data" / "wiki_infobox.json"


def delink(s: str) -> str:
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{(?:NFL|AFL) ?Year\|(\d{4})(?:\|(\d{4}))?\}\}", lambda m: m.group(1) + ("–" + m.group(2) if m.group(2) else ""), s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    return s


def years_in(s: str) -> list[int]:
    out = set()
    for a, b in re.findall(r"(19[5-9]\d|20[0-2]\d)\s*(?:[–\-]\s*(19[5-9]\d|20[0-2]\d))?", s):
        a = int(a)
        b = int(b) if b else a
        if 0 <= b - a <= 20:
            out.update(range(a, b + 1))
    return sorted(out)


def field(box: str, name: str) -> str | None:
    m = re.search(r"\|\s*" + name + r"\s*=\s*(.*)", box)
    return m.group(1).strip() if m else None


NICK_CODE = {
    "Cardinals": "ARI", "Falcons": "ATL", "Ravens": "BAL", "Bills": "BUF", "Panthers": "CAR", "Bears": "CHI",
    "Bengals": "CIN", "Browns": "CLE", "Cowboys": "DAL", "Broncos": "DEN", "Lions": "DET", "Packers": "GB",
    "Colts": "IND", "Jaguars": "JAX", "Chiefs": "KC", "Chargers": "LAC", "Rams": "LAR", "Raiders": "LV",
    "Dolphins": "MIA", "Vikings": "MIN", "Patriots": "NE", "Saints": "NO", "Giants": "NYG", "Jets": "NYJ",
    "Eagles": "PHI", "Steelers": "PIT", "Seahawks": "SEA", "49ers": "SF", "Buccaneers": "TB", "Oilers": "TEN",
    "Redskins": "WAS", "Commanders": "WAS", "Football Team": "WAS",
}
FULL_CODE = {"New York Titans": "NYJ", "Tennessee Titans": "TEN", "Dallas Texans": "KC", "Houston Texans": "HOU",
             "New York Giants": "NYG", "Washington Football Team": "WAS"}


def team_code(name: str):
    name = re.sub(r"\s*\(.*$", "", name).strip()
    if name in FULL_CODE:
        return FULL_CODE[name]
    if name.endswith("Titans") or name.endswith("Texans"):
        return None
    for nick, code in NICK_CODE.items():
        if name.endswith(" " + nick):
            # NFL/AFL franchises only (e.g. not "BC Lions", "Hamilton Tiger-Cats", "Saskatchewan Roughriders")
            if nick in ("Lions",) and not name.startswith("Detroit"):
                return None
            if nick == "Giants" and not name.startswith("New York"):
                return None
            if nick == "Cardinals" and not re.match(r"(Chicago|St\. Louis|Phoenix|Arizona)", name):
                return None
            return code
    return None


def past_teams(box: str) -> list:
    m = re.search(r"\|\s*pastteams\s*=(.*?)(?=\n\s*\|\s*[a-z_]+\s*=)", box, flags=re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).split("\n"):
        line = line.strip()
        if not line.startswith("*"):
            continue
        if re.search(r"\)\s*\*+\s*$", line) or line.endswith("*"):
            continue  # "*" = offseason / practice squad member only (no number in the list)
        link = re.search(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]", line)
        name = (link.group(2) or link.group(1)) if link else delink(line.lstrip("* "))
        out.append(name.strip())
    return out


def parse(box: str) -> dict:
    rec = {}
    end = box.find("\n}}")
    box = box[: end if end > 0 else len(box)]
    n = field(box, "number")
    if n:
        n = delink(n)
        n = re.sub(r"'''?", "", n)
        nums = [int(x) for x in re.findall(r"\b(\d{1,2})\b", n)]
        if nums:
            rec["num"] = nums
            # numbers listed in the same order as the past-teams list -> per-franchise number
            pt = past_teams(box)
            if len(pt) == len(nums) and len(nums) > 1:
                per = {}
                for team, n_ in zip(pt, nums):
                    c = team_code(team)
                    if c is None:
                        continue
                    per.setdefault(c, set()).add(n_)
                tn = {c: list(v)[0] for c, v in per.items() if len(v) == 1}
                if tn:
                    rec["team_num"] = tn
    p = field(box, "position")
    if p:
        rec["pos"] = delink(p).split("/")[0].split(",")[0].split("<")[0].strip()
    afl, pb = set(), set()
    for line in box.split("\n"):
        if not line.lstrip().startswith("*"):
            continue
        d = delink(line)
        if "CFL" in d or "college" in d.lower():
            continue
        par = d[d.find("("):] if "(" in d else ""
        if re.search(r"AFL All-Star|American Football League All-Star", d):
            afl.update(years_in(par))
        elif re.search(r"Pro Bowl", d) and not re.search(r"MVP|Hall", d):
            pb.update(years_in(par))
    if afl:
        rec["afl_as"] = sorted(afl)
    if pb:
        rec["pb"] = sorted(pb)
    return rec


def main():
    out = {}
    for raw_path in RAWS:
        if not raw_path.exists():
            continue
        raw = json.loads(raw_path.read_text())
        for t, v in raw.items():
            if v.startswith("{{Infobox"):
                r = parse(v)
            elif v.startswith("highlights"):  # highlights-only snippet (older cache format)
                r = parse("| " + v)
                r.pop("num", None)
                r.pop("pos", None)
            else:
                continue
            if r:
                base = out.setdefault(t, {})
                for k, val in r.items():
                    if k in ("afl_as", "pb"):
                        base[k] = sorted(set(base.get(k, [])) | set(val))
                    else:
                        base.setdefault(k, val)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, sort_keys=True, separators=(",", ":")))
    print("infobox facts", len(out), "->", OUT)


if __name__ == "__main__":
    main()
