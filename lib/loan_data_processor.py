import os
import pandas as pd
from pathlib import Path
import shutil
import urllib
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

RENAME_MAP = {
    "Common Code": "CommonCode",
    "Instrument Type": "InstrumentType",
    "Security Name": "SecurityName",
    "Rate Change or Loan Value Change": "RateChange",
    "Loan Type": "LoanType",
    "Mat Type": "MatType",
    "Lender/Borrower": "LenderBorrower",
    "Loan Reference": "LoanReference",
    "Loan Opening Date": "LoanOpeningDate",
    "Loan Closing Date": "LoanClosingDate",
    "Loan Quantity": "LoanQuantity",
    "Loan Quantity Type": "LoanQuantityType",
    "Loan Value Currency": "LoanValueCurrency",
    "Loan Value": "LoanValue",
    "Bond Price": "BondPrice",
    "Exchange Rate: from": "ExchangeRateFrom",
    "Exchange Rate: to": "ExchangeRateTo",
    "Exchange Rate": "ExchangeRate",
    "Fee Rate": "FeeRate",
    "Handling Fee Currency": "HandlingFeeCurrency",
    "Current Commission Currency": "CurrentCommissionCurrency",
    "Accrued Commission Currency": "AccruedCommissionCurrency",
    "Current Commission Start Date": "CurrentCommissionStart",
    "Current Commission End Date": "CurrentCommissionEnd",
    "Current Commission": "CurrentCommission",
    "Accrued Commission": "AccruedCommission",
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

def get_loan_data():
    source_dir = Path(r'Y:\科組資料夾\風控企劃科\10 專案\專案-Clearstream保管業務\ASL Sample\Daily')
    dest_dir = Path('raw_data')
    os.makedirs(dest_dir, exist_ok=True)
    
    if not source_dir.exists():
        raise FileNotFoundError("source 資料夾不存在")
        
    found_files = list(source_dir.glob("*Daily*.XLS")) 
    copied_file_names = []
    
    for file_path in found_files:
        try:
            shutil.copy(file_path, dest_dir)
            copied_file_names.append({"file name": file_path.name})
        except Exception as e:
            print(f"複製 {file_path.name} 時發生錯誤: {e}")

    df_files = pd.DataFrame(copied_file_names).sort_values("file name") if copied_file_names else pd.DataFrame()
    return len(copied_file_names), df_files

def process_loan_data():
    folder = Path('raw_data')
    if not folder.exists():
        raise FileNotFoundError("raw data 資料夾不存在")

    df_list = []
    files_to_delete = []

    for file in folder.glob('*.XLS'):
        try:
            df = pd.read_excel(file, sheet_name='Loan activity', dtype={'Common Code': str})
        except ValueError:
            print(f"Skip {file.name}: worksheet 'Loan activity' not found")
            continue
        
        df.insert(0, column='Account', value=file.stem[:5])
        if "Loan Closing Date" not in df.columns:
            df.insert(12, column='Loan Closing Date', value=None)
        df_list.append(df)
        files_to_delete.append(file)

    if not df_list:
        raise ValueError("raw_data 資料夾中沒有任何 XLS 檔可供下載")

    raw_df = pd.concat(df_list, ignore_index=True).sort_values('Current Commission Start Date')
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
    filtered_df.rename(columns=RENAME_MAP, inplace=True)
    
    # 處理完後刪除原始檔案
    for f in files_to_delete:
        os.remove(f)

    return filtered_df

def upload_to_sql(filtered_df, progress_callback=None):
    if filtered_df is None or filtered_df.empty:
        raise ValueError("沒有可上傳的資料")

    params = urllib.parse.quote_plus(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=128.110.24.133;"
        "DATABASE=MIDOFFICE;"
        "TrustServerCertificate=yes;"
        "UID=fixuser;"
        "PWD=7ujm4rfv;"
    )
    
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}", fast_executemany=True)
    
    if progress_callback:
        progress_callback("正在上傳資料，請稍候...")

    success_count = 0
    duplicate_count = 0
    other_error_count = 0

    for i in range(len(filtered_df)):
        single_row_df = filtered_df.iloc[[i]]
        try:
            single_row_df.to_sql(name='HST_ASL_D', con=engine, if_exists='append', index=False)
            success_count += 1
            
        except IntegrityError:
            duplicate_count += 1
            
        except Exception as e:
            error_msg = str(e).lower()
            if any(k in error_msg for k in ["duplicate", "primary key", "23000", "unique"]):
                duplicate_count += 1
            else:
                print(f"Row {i+1}: Error occurred - {str(e)}")
                other_error_count += 1

    return success_count, duplicate_count, other_error_count