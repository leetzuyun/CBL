from sqlalchemy import create_engine
import pandas as pd
import urllib

params = urllib.parse.quote_plus(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=128.110.24.133;"
    "DATABASE=MIDOFFICE;"
    "TrustServerCertificate=yes;"
    "UID=fixuser;"
    "PWD=7ujm4rfv;"
)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

df = pd.read_csv('filtered_data.csv')

# 3. 寫入資料庫
# if_exists: 'append' 代表新增在後面，'fail' 代表如果表格存在就報錯
df.to_sql(name='HST_ASL_D', con=engine, if_exists='append', index=False)

print("匯入完成！")