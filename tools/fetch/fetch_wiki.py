import json, urllib.request, urllib.parse, time, os
UA="nfl-decade-spin-builder/1.0 (contact: longfellow85 via github MossMan85)"
def wt(title):
    u="https://en.wikipedia.org/w/api.php?"+urllib.parse.urlencode({"action":"parse","page":title,"prop":"wikitext","format":"json","formatversion":2,"redirects":1})
    for i in range(3):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=40))
            if "error" in d: return None
            return d["parse"]["wikitext"]
        except Exception as e:
            print("ERR",title,e); time.sleep(30)
found={}
for season in range(1960,2026):
    g=season+1
    titles=[f"{g} Pro Bowl", f"{g} Pro Bowl Games"]
    # AFL All-Star rosters have no per-game Wikipedia articles (titles redirect to the general article)
    for t in titles:
        p=f"wiki/{t.replace(' ','_')}.wikitext"
        if os.path.exists(p): txt=open(p).read()
        else:
            txt=wt(t); time.sleep(2.5)
            if txt: open(p,"w").write(txt)
        if txt:
            found.setdefault(str(season),[]).append(t)
    print(season, found.get(str(season)), flush=True)
json.dump(found, open("wiki/probowl_index.json","w"), indent=1)
