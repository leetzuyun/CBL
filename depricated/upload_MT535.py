from sqlalchemy import create_engine
import pandas as pd
import urllib

def upload_mt535_to_sql():
    params = urllib.parse.quote_plus(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=128.110.24.133;"
        "DATABASE=MIDOFFICE;"
        "TrustServerCertificate=yes;"
        "UID=fixuser;"
        "PWD=7ujm4rfv;"
    )
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

    df = pd.read_csv('test.csv')
    filtered_df = df.drop_duplicates(
        subset=['Account', 'Pos_date'], 
        keep='last'
    )
    # 3. 寫入資料庫
    filtered_df.to_sql(name='HST_MT535_D', con=engine, if_exists='append', index=False)

if __name__ == "__main__":
    upload_mt535_to_sql()