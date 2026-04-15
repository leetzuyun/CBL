import os
import pandas as pd
from pathlib import Path

rename_map={
    "Common Code":"CommonCode",
    "Instrument Type":"InstrumentType",
    "Security Name":"SecurityName",
    "Rate Change or Loan Value Change":"RateChange",
    "Loan Type":"LoanType",
    "Mat Type":"MatType",
    "Lender/Borrower":"LenderBorrower",
    "Loan Reference":"LoanReference",
    "Loan Opening Date":"LoanOpeningDate",
    "Loan Closing Date":"LoanClosingDate",
    "Loan Quantity":"LoanQuantity",
    "Loan Quantity Type":"LoanQuantityType",
    "Loan Value Currency":"LoanValueCurrency",
    "Loan Value":"LoanValue",
    "Bond Price":"BondPrice",
    "Exchange Rate: from":"ExchangeRateFrom",
    "Exchange Rate: to":"ExchangeRateTo",
    "Exchange Rate":"ExchangeRate",
    "Fee Rate":"FeeRate",
    "Handling Fee Currency":"HandlingFeeCurrency",
    "Current Commission Currency":"CurrentCommissionCurrency",
    "Accrued Commission Currency":"AccruedCommissionCurrency",
    "Current Commission Start Date":"CurrentCommissionStart",
    "Current Commission End Date":"CurrentCommissionEnd",
    "Current Commission":"CurrentCommission",
    "Accrued Commission":"AccruedCommission",

}

def filter_data(row):
    start = pd.to_datetime(row['Current Commission Start Date'])
    end = pd.to_datetime(row['Current Commission End Date'])
    
    date_range = pd.date_range(start=start, end=end)
    n = len(date_range)
    
    expanded_rows = []
    
    daily_curr_comm = row['Current Commission'] / n
    original_accrued = row['Accrued Commission']
    
    for i, current_date in enumerate(date_range):
        new_row = row.copy()
        
        new_row['Current Commission Start Date'] = current_date
        new_row['Current Commission End Date'] = current_date
        
        new_row['Current Commission'] = daily_curr_comm

        new_row['Accrued Commission'] = original_accrued - (n - 1 - i) * daily_curr_comm
        
        expanded_rows.append(new_row)
        
    return pd.DataFrame(expanded_rows)


folder = Path('raw_data')

df_list = []

for file in folder.glob('*.XLS'):
    try:
        df = pd.read_excel(file, sheet_name='Loan activity')
    except ValueError:
        print(f"⚠️ Skip {file.name}: worksheet 'Loan activity' not found")
        continue
    df.insert(0, column='Account', value=file.stem[:5])
    if "Loan Closing Date" not in df.columns:
        df.insert(12, column='Loan Closing Date', value=None)
    df_list.append(df)
    if os.path.exists(file):
        os.remove(file)

if df_list:
    raw_df = pd.concat(df_list, ignore_index=True).sort_values('Current Commission Start Date')
    # print(raw_df)
if not df_list:
    raise RuntimeError("raw_data 資料夾中沒有任何 XLS 檔案")


raw_df['Current Commission Start Date'] = pd.to_datetime(raw_df['Current Commission Start Date'])
raw_df['Current Commission End Date'] = pd.to_datetime(raw_df['Current Commission End Date'])

mask = raw_df["Current Commission End Date"] != raw_df["Current Commission Start Date"]

to_process = raw_df[mask]
no_process = raw_df[~mask]

if not to_process.empty:
    processed_list = [filter_data(row) for _, row in to_process.iterrows()]
    processed_df = pd.concat(processed_list, ignore_index=True)
    filtered_df = pd.concat([no_process, processed_df], ignore_index=True).sort_values(by=['Current Commission Start Date'])
else:
    filtered_df = raw_df
filtered_df.insert(0, column='Pos_date', value=filtered_df['Current Commission Start Date'])
filtered_df.rename(columns=rename_map, inplace=True)
filtered_df.to_csv('filtered_data.csv', index=False)
print("Data has been saved to 'filtered_data.csv'")