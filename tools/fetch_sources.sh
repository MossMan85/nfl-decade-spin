#!/usr/bin/env bash
# Rebuild the raw source cache used by tools/extract_history.py (default cache dir /tmp/nfldata).
# Every step is resumable (cached files are skipped). Be polite: the crawlers pace themselves.
#
#   1. nflverse rosters 1960-2025 + player stats 1999-2025         (tools/fetch/dl_nflverse.sh)
#   2. footballdb.com team-season roster + stats pages 1960-2025   (tools/fetch/crawl_fdb.py)
#      roster: jersey (1975+), listed position, G, GS (~1981+); stats: passing..returns, defense
#   3. footballdb.com awards: AP All-Pro 1960-2025, AP All-AFL 1960-69, PFWA, Hall of Fame,
#      all-decade teams                                            (tools/fetch/crawl_awards.py)
#   4. Wikipedia Pro Bowl articles (rosters) 1960-2025              (tools/fetch/fetch_wiki.py)
#   5. Wikidata: DB position labels + enwiki titles with birth dates (tools/fetch/wd2.py, wd3.py)
#   6. Wikipedia infoboxes for pre-1975 players (AFL All-Star years, jersey, position)
#                                                                   (tools/fetch/fetch_wiki_players.py)
# Then:
#   python3 tools/extract_history.py      # cache -> tools/data/player_seasons.json.gz (committed)
#   python3 tools/wiki_infobox.py         # infobox cache -> tools/data/wiki_infobox.json (committed)
#   python3 tools/extract_history.py      # (re-run so infobox facts are merged)
#   python3 tools/build_roster.py         # tools/data/* + curated files -> nfl-data.js
#   node tools/coverage_audit.js          # must report 0 gaps / 0 problems
set -euo pipefail
CACHE=${NFLDATA:-/tmp/nfldata}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$CACHE"/{rosters,stats,fdb,fdb_awards,wiki,wiki_players}
cd "$CACHE"
bash "$HERE/fetch/dl_nflverse.sh"
python3 "$HERE/fetch/crawl_fdb.py" 1960 1998 roster,stats
python3 "$HERE/fetch/crawl_fdb.py" 1999 2025 roster
python3 "$HERE/fetch/crawl_awards.py"
python3 "$HERE/fetch/fetch_wiki.py"
python3 "$HERE/fetch/wd2.py"
python3 "$HERE/fetch/wd3.py"
python3 "$HERE/extract_history.py"
python3 "$HERE/fetch/fetch_wiki_players.py" "$HERE/data/player_seasons.json.gz"
python3 "$HERE/wiki_infobox.py"
python3 "$HERE/extract_history.py"
python3 "$HERE/build_roster.py"
node "$HERE/coverage_audit.js" --quiet
