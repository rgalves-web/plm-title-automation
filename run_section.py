"""Standalone one-section runsheet builder.
Bypasses the app pipeline. Reads the package, OCRs scans, extracts template-grade
conveyance + comments, writes into a COPY of the MOR template, and prints a loud
completion + coverage report so you SEE when it finished.

Usage:
  python run_section.py --package PKG.zip --template TEMPLATE.xlsx --out OUT.xlsx
                        [--limit N] [--llm]
"""
from __future__ import annotations
import argparse, io, os, re, sys, time, zipfile, shutil
import pandas as pd, fitz, pytesseract
from PIL import Image
import openpyxl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from title_extractor import extract

TYPEMAP = {'DEDMIN':'Mineral Deed','DEDWAR':'Warranty Deed','DEDQCL':'Quit Claim Deed',
           'DED':'Deed','OGL':'Oil and Gas Lease','PAT':'Patent','DEDPRP':'Personal Representative Deed',
           'DEDPTR':"Public Trustee's Deed",'ROYDED':'Royalty Deed'}
CONVEY_TYPES = set(TYPEMAP.values())

def _key(v): return re.sub(r'[^0-9]','', re.sub(r'^[A-Za-z]+','', str(v)))

def ocr_text(zf, member, max_pages=1):
    d = fitz.open(stream=zf.read(member), filetype='pdf'); out=[]
    for p in d[:max_pages]:
        pix = p.get_pixmap(dpi=300)
        out.append(pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes('png')))))
    d.close(); return '\n'.join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', required=True); ap.add_argument('--template', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--sheet', default='Runsheet - NE')
    a = ap.parse_args()

    zf = zipfile.ZipFile(a.package)
    csv = [n for n in zf.namelist() if n.lower().endswith('documentlist.csv') and 'fpr' not in n.lower()]
    csv = csv[0] if csv else [n for n in zf.namelist() if n.lower().endswith('.csv')][0]
    df = pd.read_csv(io.BytesIO(zf.read(csv)))
    df['DT'] = df['Doc Type'].astype(str).str.upper().map(lambda c: TYPEMAP.get(c, ''))
    work = df[df['DT'] != ''].copy()
    if a.limit: work = work.head(a.limit)

    pdfs = {}
    for n in zf.namelist():
        if n.lower().endswith('.pdf') and 'section reports' in n.lower() and 'fpr' not in n.lower():
            pdfs.setdefault(_key(os.path.splitext(n.split('/')[-1])[0]), n)

    shutil.copy(a.template, a.out)
    wb = openpyxl.load_workbook(a.out); ws = wb[a.sheet]
    start = 3
    total = len(work); done = 0; conv_hits = 0; com_hits = 0; t0 = time.time()
    print(f"[START] {total} conveyance-bearing instruments to process from {os.path.basename(csv)}", flush=True)

    r = start
    for i, (_, row) in enumerate(work.iterrows(), 1):
        member = pdfs.get(_key(row['Reception Number']))
        txt = ocr_text(zf, member) if member else ''
        tf = extract(row['DT'], txt)
        ws.cell(r,1).value = float(i)
        ws.cell(r,2).value = row['DT']
        ws.cell(r,3).value = str(row['Reception Number'])
        ws.cell(r,6).value = row.get('Recording Date')
        ws.cell(r,7).value = str(row.get('Grantor','')).strip('"')
        ws.cell(r,8).value = str(row.get('Grantee','')).strip('"')
        if tf.acreage: ws.cell(r,9).value = tf.acreage
        ws.cell(r,10).value = tf.conveyance            # CONVEYANCE
        ws.cell(r,11).value = "\n\n".join(tf.comments) if tf.comments else None  # COMMENTS (analysis only)
        if tf.conveyance and 'ownship' in tf.conveyance: conv_hits += 1
        if tf.comments: com_hits += 1
        done += 1; r += 1
        print(f"  [{i}/{total}] {row['DT']:<20} {row['Reception Number']}  conv={'Y' if tf.conveyance else '-'} com={'Y' if tf.comments else '-'}", flush=True)

    wb.save(a.out)
    dt = time.time() - t0
    print("="*60, flush=True)
    print(f"[DONE] wrote {done} rows to {a.out} in {dt:.0f}s", flush=True)
    print(f"[COVERAGE] conveyance w/ legal: {conv_hits}/{done} ({100*conv_hits//max(done,1)}%) | comments: {com_hits}/{done} ({100*com_hits//max(done,1)}%)", flush=True)
    print("="*60, flush=True)

if __name__ == '__main__':
    main()
