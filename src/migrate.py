"""Bronze->silver curation with a snapshot manifest, mirroring Iceberg semantics locally."""
import csv, json, argparse, pathlib, hashlib, datetime
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",default="data/raw"); ap.add_argument("--output",default="data/curated"); a=ap.parse_args()
    rows=list(csv.DictReader(open(pathlib.Path(a.input)/"transactions.csv")))
    assert rows, "no input rows"
    for r in rows:
        assert int(r["qty"])>0, "data quality: qty must be positive"
    out=pathlib.Path(a.output); out.mkdir(parents=True,exist_ok=True)
    with open(out/"curated.csv","w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=rows[0].keys()); wr.writeheader(); wr.writerows(rows)
    snap={"snapshot_id":hashlib.sha256(str(len(rows)).encode()).hexdigest()[:12],
          "created_at":datetime.datetime.utcnow().isoformat(),"rows":len(rows),"parent":None}
    (out/"snapshot.json").write_text(json.dumps(snap,indent=2)); print(snap)
if __name__=="__main__": main()
