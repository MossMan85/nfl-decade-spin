import json, urllib.request, urllib.parse
q = """
SELECT ?article ?dob WHERE {
  ?p wdt:P106 wd:Q19204627; wdt:P569 ?dob.
  ?article schema:about ?p; schema:isPartOf <https://en.wikipedia.org/>.
}
"""
u="https://query.wikidata.org/sparql?"+urllib.parse.urlencode({"query":q,"format":"json"})
d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"nfl-decade-spin-builder/1.0 (github MossMan85)"}),timeout=300))
rows=[]
for b in d["results"]["bindings"]:
    t=urllib.parse.unquote(b["article"]["value"].split("/wiki/")[-1]).replace("_"," ")
    rows.append({"title":t,"dob":b["dob"]["value"][:10]})
json.dump(rows,open("/tmp/nfldata/wikidata_enwiki_dob.json","w"))
print(len(rows), rows[:3])
