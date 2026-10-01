#!/usr/bin/env node
/**
 * Coverage audit for NFL Decade Spin.
 *   node tools/coverage_audit.js [path/to/nfl-data.js] [--json out.json] [--quiet]
 *
 * For every franchise and every decade it actually played in (AFL seasons count;
 * expansion teams from their first season; Browns 1996-98 gap), lists every
 * rosterDB key the game can ask for and how many players it holds (target = 3).
 * Existence is defined here independently of the data file so a missing key can
 * never masquerade as "team didn't exist".
 * Also runs sanity checks: duplicates within a key, season year inside the decade,
 * card position consistent with the slot, no players for decades a team didn't exist.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const args = process.argv.slice(2);
const jsonOut = args.includes("--json") ? args[args.indexOf("--json") + 1] : null;
const file = args.find((a, i) => !a.startsWith("--") && args[i - 1] !== "--json") || path.join(__dirname, "..", "nfl-data.js");
const quiet = args.includes("--quiet");

const ctx = { window: {} };
vm.runInNewContext(fs.readFileSync(file, "utf8"), ctx);
const DATA = ctx.window.NFL_DATA;

const DECADES = ["1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"];
// First season of each modern franchise (lineage folded in; AFL years count).
const FOUNDING = {
  ARI: 1920, ATL: 1966, BAL: 1996, BUF: 1960, CAR: 1995, CHI: 1920, CIN: 1968, CLE: 1946,
  DAL: 1960, DEN: 1960, DET: 1930, GB: 1919, HOU: 2002, IND: 1953, JAX: 1995, KC: 1960,
  LAC: 1960, LAR: 1936, LV: 1960, MIA: 1966, MIN: 1961, NE: 1960, NO: 1967, NYG: 1925,
  NYJ: 1960, PHI: 1933, PIT: 1933, SEA: 1976, SF: 1946, TB: 1976, TEN: 1960, WAS: 1932,
};
const GAPS = { CLE: [1996, 1997, 1998] };
const LAST_SEASON = 2025;

const OFF2 = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "LT", "LG", "C", "RG", "RT"];
const OFF1 = ["QB", "RB", "WR1", "WR2", "WR3", "TE", "LT", "LG", "C", "RG", "RT"];
const D43 = ["LDE", "LDT", "RDT", "RDE", "WLB", "MLB", "SLB", "LCB", "RCB", "SS", "FS"];
const D34 = ["LE", "NT", "RE", "LOLB", "LILB", "RILB", "ROLB", "LCB", "RCB", "SS", "FS"];
const ST = ["K", "P", "RET"];
const SLOTS = [...new Set([...OFF2, ...OFF1, ...D43, ...D34, ...ST])];

// Card position (p.pos) allowed for each slot. Positions are strictly locked.
const ALLOWED = {
  QB: ["QB"], RB: ["RB", "FB", "HB"], RB1: ["RB", "FB", "HB"], RB2: ["RB", "FB", "HB"],
  WR1: ["WR"], WR2: ["WR"], WR3: ["WR"], TE: ["TE"],
  LT: ["OT"], RT: ["OT"], LG: ["G", "OG"], RG: ["G", "OG"], C: ["C"],
  LDE: ["DE"], RDE: ["DE"], LE: ["DE"], RE: ["DE"], LDT: ["DT"], RDT: ["DT"], NT: ["DT", "NT"],
  WLB: ["OLB", "LB"], SLB: ["OLB", "LB"], LOLB: ["OLB", "LB"], ROLB: ["OLB", "LB"],
  MLB: ["MLB", "ILB", "LB"], LILB: ["MLB", "ILB", "LB"], RILB: ["MLB", "ILB", "LB"],
  LCB: ["CB"], RCB: ["CB"], SS: ["SS", "S", "FS"], FS: ["FS", "S", "SS"],
  K: ["K"], P: ["P"], RET: null, // returner can be any position
};

function seasons(team, dec) {
  const s = parseInt(dec, 10);
  const ys = [];
  for (let y = s; y < s + 10; y++) {
    if (y >= FOUNDING[team] && y <= LAST_SEASON && !(GAPS[team] || []).includes(y)) ys.push(y);
  }
  return ys;
}

const teams = Object.keys(FOUNDING).sort();
const gaps = [];
const problems = [];
let keys = 0, full = 0;
const hist = { 0: 0, 1: 0, 2: 0, 3: 0, more: 0 };
const perTeamDecade = {};

for (const t of teams) {
  for (const d of DECADES) {
    const ys = seasons(t, d);
    for (const slot of SLOTS) {
      const list = DATA.rosterDB[`${t}|${d}|${slot}`];
      if (!ys.length) {
        if (Array.isArray(list) && list.length) problems.push(`${t}|${d}|${slot}: has players but franchise did not play`);
        continue;
      }
      keys++;
      const n = Array.isArray(list) ? list.length : 0;
      hist[n > 3 ? "more" : n]++;
      if (n >= 3) full++;
      else {
        gaps.push({ key: `${t}|${d}|${slot}`, have: n });
        perTeamDecade[`${t} ${d}`] = (perTeamDecade[`${t} ${d}`] || 0) + 1;
      }
      if (!Array.isArray(list)) continue;
      const names = new Set();
      for (const p of list) {
        if (!p || !p.name) { problems.push(`${t}|${d}|${slot}: empty card`); continue; }
        if (names.has(p.name)) problems.push(`${t}|${d}|${slot}: duplicate ${p.name}`);
        names.add(p.name);
        const yr = parseInt(p.season, 10);
        if (!(yr >= parseInt(d, 10) && yr <= parseInt(d, 10) + 9)) problems.push(`${t}|${d}|${slot}: ${p.name} season ${p.season} outside decade`);
        else if (!ys.includes(yr)) problems.push(`${t}|${d}|${slot}: ${p.name} season ${yr} not a franchise season`);
        const allowed = ALLOWED[slot];
        if (allowed && p.pos && !allowed.includes(p.pos)) problems.push(`${t}|${d}|${slot}: ${p.name} pos ${p.pos}`);
        if (p.rating != null && !(p.rating >= 40 && p.rating <= 99)) problems.push(`${t}|${d}|${slot}: ${p.name} rating ${p.rating}`);
      }
    }
  }
}

const report = { file, keys, full, gaps: gaps.length, hist, problems: problems.length, gapList: gaps, problemList: problems };
console.log(`Coverage audit: ${path.basename(file)}`);
console.log(`  team-decade-slot keys that must exist: ${keys}`);
console.log(`  keys with >=3 players: ${full}`);
console.log(`  GAPS (<3 players): ${gaps.length}   [0:${hist[0]} 1:${hist[1]} 2:${hist[2]}]`);
console.log(`  sanity problems: ${problems.length}`);
if (!quiet) {
  const top = Object.entries(perTeamDecade).sort((a, b) => b[1] - a[1]);
  if (top.length) console.log("  team-decades with most gaps: " + top.slice(0, 15).map(([k, v]) => `${k}=${v}`).join(", "));
  for (const g of gaps.slice(0, 400)) console.log(`  GAP ${g.key} has ${g.have}`);
  for (const p of problems.slice(0, 200)) console.log(`  PROBLEM ${p}`);
}
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify(report, null, 1));
process.exitCode = gaps.length || problems.length ? 1 : 0;
