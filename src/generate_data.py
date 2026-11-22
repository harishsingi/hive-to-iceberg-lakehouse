"""Generate synthetic parts/service transactions. No real employer data."""
import csv, random, argparse, pathlib, datetime
random.seed(42)
PARTS=["brake pad","filter","battery","alternator","sensor","pump"]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--rows",type=int,default=1000); ap.add_argument("--out",default="data/raw"); a=ap.parse_args()
    out=pathlib.Path(a.out); out.mkdir(parents=True,exist_ok=True)
    with open(out/"transactions.csv","w",newline="") as f:
        wr=csv.writer(f); wr.writerow(["txn_id","part","dealer_region","qty","txn_date"])
        for i in range(a.rows):
            d=datetime.date(2024,1,1)+datetime.timedelta(days=random.randint(0,700))
            wr.writerow([i,random.choice(PARTS),random.choice(["SE","NE","MW","W"]),random.randint(1,20),d.isoformat()])
    print(f"wrote {a.rows} rows")
if __name__=="__main__": main()
