for y in $(seq 1960 2025); do f=rosters/roster_$y.csv; [ -s $f ] || curl -sfL -o $f https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_$y.csv; done
for y in $(seq 1999 2025); do f=stats/stats_player_reg_$y.csv; [ -s $f ] || curl -sfL -o $f https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_$y.csv; done
echo DL_DONE
