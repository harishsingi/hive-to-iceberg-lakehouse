import csv, subprocess, sys, pathlib
def test_pipeline(tmp_path):
    subprocess.check_call([sys.executable,"-m","src.generate_data","--rows","50","--out",str(tmp_path/"raw")])
    rows=list(csv.DictReader(open(tmp_path/"raw"/"transactions.csv"))); assert len(rows)==50
