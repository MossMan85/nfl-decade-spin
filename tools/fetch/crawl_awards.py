import time, os, urllib.request
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
urls=[]
for y in range(1960,2026): urls.append(f"ap-nfl-all-pro-team/{y}")
for y in range(1960,1970): urls.append(f"ap-all-afl-team/{y}")
for y in range(1960,2026): urls.append(f"pfwa-nfl-all-pro-team/{y}")
urls += ["pro-football-hall-of-fame"] + [f"nfl-{d}s-all-decade-team" for d in range(1960,2020,10)] + ["afl-alltime-team"]
for u in urls:
    p="/tmp/nfldata/fdb_awards/"+u.replace("/","_")+".html"
    if os.path.exists(p): continue
    for i in range(3):
        try:
            h=urllib.request.urlopen(urllib.request.Request("https://www.footballdb.com/awards/"+u,headers={"User-Agent":UA}),timeout=40).read().decode("utf-8","ignore")
            if "Just a moment" in h[:3000]: raise Exception("challenge")
            open(p,"w").write(h); break
        except Exception as e:
            print("ERR",u,e,flush=True); time.sleep(15)
    time.sleep(2)
print("AWARDS_DONE",flush=True)
