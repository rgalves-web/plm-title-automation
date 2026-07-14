import openpyxl, sys
path = sys.argv[1]
wb = openpyxl.load_workbook(path, data_only=True)
ws = wb.active
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0 or row[0] == "ERROR":
        print(row)
