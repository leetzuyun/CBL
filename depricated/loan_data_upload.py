# db_uploader.py
import urllib
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

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