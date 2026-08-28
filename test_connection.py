"""Quick check that credentials + sheet id work. Run:  python test_connection.py"""

import gspread
from analytics import SERVICE_ACCOUNT, SHEET_KEY

gc = gspread.service_account(filename=SERVICE_ACCOUNT)
sh = gc.open_by_key(SHEET_KEY)

print("Connected! Tabs found:")
for ws in sh.worksheets():
    print(" -", ws.title)
