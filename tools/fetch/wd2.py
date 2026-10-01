import json, urllib.request, urllib.parse
q = """
SELECT ?p ?pLabel ?dob ?pos WHERE {
  VALUES ?pos { wd:Q869161 wd:Q24994 wd:Q3500542 wd:Q3087299 wd:Q674953 }
  ?p wdt:P106 wd:Q19204627; wdt:P413 ?pos.
  OPTIONAL { ?p wdt:P569 ?dob. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
u="https://query.wikidata.org/sparql?"+urllib.parse.urlencode({"query":q,"format":"json"})
d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"nfl-decade-spin-builder/1.0 (github MossMan85)"}),timeout=180))
code={"Q869161":"CB","Q24994":"S","Q3500542":"SS","Q3087299":"FS","Q674953":"DB"}
rows=[]
for b in d["results"]["bindings"]:
    rows.append({"qid":b["p"]["value"].split("/")[-1],"name":b["pLabel"]["value"],"dob":b.get("dob",{}).get("value","")[:10],"pos":code[b["pos"]["value"].split("/")[-1]]})
json.dump(rows,open("/tmp/nfldata/wikidata_db_pos.json","w"))
print(len(rows))
