import gzip, json, os, time, urllib.request, urllib.parse, sys
UA="nfl-decade-spin-builder/1.0 (github MossMan85)"
rows=json.load(gzip.open(sys.argv[1],"rt"))
titles=sorted({r["wiki"] for r in rows if r.get("wiki") and r["year"]<1975})
os.makedirs("/tmp/nfldata/wiki_players",exist_ok=True)
out="/tmp/nfldata/wiki_players/infobox_pre1975.json"
have=json.load(open(out)) if os.path.exists(out) else {}
todo=[t for t in titles if not have.get(t)]
print("titles",len(titles),"todo",len(todo),flush=True)
for i in range(0,len(todo),40):
    batch=todo[i:i+40]
    q={"action":"query","prop":"revisions","rvprop":"content","rvslots":"main","format":"json","formatversion":2,"redirects":1,"titles":"|".join(batch)}
    u="https://en.wikipedia.org/w/api.php?"+urllib.parse.urlencode(q)
    d=None
    for a in range(5):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=60)); break
        except Exception as e:
            print("ERR",e,flush=True); time.sleep(60)
    if d is None:
        continue
    norm={x["from"]:x["to"] for x in d["query"].get("normalized",[])+d["query"].get("redirects",[])}
    pages={p["title"]:p for p in d["query"]["pages"]}
    for t in batch:
        tt=norm.get(t,t); tt=norm.get(tt,tt)
        p=pages.get(tt)
        txt=p["revisions"][0]["slots"]["main"]["content"] if p and p.get("revisions") else ""
        # keep only the infobox highlights region to stay small
        j=txt.find("{{Infobox")
        have[t]=txt[j:j+6000] if j>=0 else "(no infobox)"
    json.dump(have,open(out,"w"))
    time.sleep(6)
print("done",len(have))
