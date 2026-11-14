GC Responder Intact Stability Tool (GM + Allowable VCG)

What this does:
- Sums weights (lightship + optional added weight + tanks)
- Computes KG/LCG, free-surface correction (FSC), GMt = KMt - KG - FSC
- Interpolates mean draft, LCB, MCT, KMt from hydrostatics by displacement
- Computes trim (ft, +aft) from disp*(LCG-LCB)/MCT
- Checks KG against the 'Maximum Allowable VCG' curve (No Trim only)

Quick start (Windows/Mac/Linux):
1) Install Python 3.11+ from python.org
2) Open a terminal in this folder
3) Install:
   pip install -r requirements.txt
4) Run:
   streamlit run app.py

Data files:
- data/hydrostatics.csv      (generated from your hydrostatic table screenshot via OCR; verify values)
- data/allowable_vcg.csv     (from your uploaded 'Maximum VSG No Trim.csv')
- data/tanks.json            (placeholder; replace with real tank sounding/weight and FSM)

If you want a single-click executable (Windows):
1) pip install pyinstaller
2) pyinstaller --onefile --add-data "data;data" app.py
3) Run dist/app.exe
