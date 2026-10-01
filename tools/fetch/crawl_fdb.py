import re, time, os, sys, urllib.request
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
OUT="/tmp/nfldata/fdb"
def get(url, path, tries=4):
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return open(path, encoding="utf-8", errors="ignore").read()
    for i in range(tries):
        try:
            req=urllib.request.Request(url, headers={"User-Agent":UA})
            h=urllib.request.urlopen(req, timeout=40).read().decode("utf-8","ignore")
            if "Just a moment" in h[:3000] or len(h)<8000: raise Exception("challenge/short")
            open(path,"w").write(h); time.sleep(1.2); return h
        except Exception as e:
            print("ERR",url,e,flush=True); time.sleep(10*(i+1))
    return ""
y0=int(sys.argv[1]); y1=int(sys.argv[2]); kinds=sys.argv[3].split(",")
for y in range(y0,y1+1):
    slugs=set()
    for lg in (["NFL","AFL"] if y<=1969 else ["NFL"]):
        h=get(f"https://www.footballdb.com/standings/index.html?lg={lg}&yr={y}", f"{OUT}/standings_{lg}_{y}.html")
        for m in re.finditer(r'href="/teams/(nfl|afl)/([a-z0-9-]+)/results/%d"'%y, h):
            slugs.add((m.group(1), m.group(2)))
    print(y, len(slugs), flush=True)
    for lg, s in sorted(slugs):
        for k in kinds:
            get(f"https://www.footballdb.com/teams/{lg}/{s}/{k}/{y}", f"{OUT}/{k}_{y}_{lg}_{s}.html")
print("DONE")
