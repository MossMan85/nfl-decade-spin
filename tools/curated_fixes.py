"""Hand corrections applied on top of the sourced data (fan review).

FORCE_EXCLUDE: (footballdb_id, team, year) rows to drop (e.g. source mis-attribution).
POS_OVERRIDE:  (footballdb_id, team, year) -> position group, when the source label is wrong
               or too generic and the real position is documented.
"""
FORCE_EXCLUDE: set = set()
POS_OVERRIDE: dict = {
    # Joe Klecko was the Jets' right defensive end 1977-82 ("New York Sack Exchange"); the
    # season labels for 1977 and 1979 say DT. He moved inside (DT/NT) from 1983.
    ("joe-klecko-kleckjo01", "NYJ", 1977): "DE",
    ("joe-klecko-kleckjo01", "NYJ", 1979): "DE",
}
