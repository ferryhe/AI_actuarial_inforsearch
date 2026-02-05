import sqlite3
import os
from pathlib import Path

db_path = "data/index.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# URL from the log that failed
target_url = "https://www.soa.org/4ac521/globalassets/assets/files/edu/2023/fall/exams/fall-2023-ghdp-exam.xlsx"

print(f"Checking URL: {target_url}")
cur = conn.execute("SELECT local_path FROM files WHERE url = ?", (target_url,))
row = cur.fetchone()

if row:
    local_path = row['local_path']
    print(f"DB local_path: {local_path!r}")
    
    p = Path(local_path)
    print(f"Path object: {p}")
    print(f"Absolute path: {p.resolve()}")
    print(f"Exists? {p.exists()}")
    
    if not p.exists():
        # Try prepending current dir
        cwd = Path.cwd()
        p2 = cwd / local_path
        print(f"Trying with CWD ({cwd}): {p2}")
        print(f"Exists? {p2.exists()}")
        
        # Try checking if file is mostly there but path separator issue?
        # Windows uses \, db seems to have \ (escaped in python output)
        pass
else:
    print("URL not found in DB")

# Check a PDF that failed too
target_pdf = "https://www.soa.org/4ac521/globalassets/assets/files/edu/2023/fall/exams/fall-2023-ghdp-exam.pdf"
print(f"\nChecking PDF: {target_pdf}")
cur = conn.execute("SELECT local_path FROM files WHERE url = ?", (target_pdf,))
row = cur.fetchone()
if row:
    local_path = row['local_path']
    print(f"DB local_path: {local_path!r}")
    p = Path(local_path)
    print(f"Exists? {p.exists()}")
    
conn.close()
