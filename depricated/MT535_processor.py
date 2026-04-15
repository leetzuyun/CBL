from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine
import urllib

def process_MT535_html():  
    def parse_mt535_html(file_path):
        content = Path(file_path).read_text(encoding='utf-8')
        soup = BeautifulSoup(content, 'lxml')
        tables = soup.find_all('table')
        
        data = {}

        def clean_num(raw_text):
            clean_str = raw_text.replace(',', '')
            return pd.to_numeric(clean_str, errors='coerce')

        try:
            # 1. Statement Date (第 2 個 table -> 第 2 個 td -> 取文字)
            # 結構: <table>...<tr><td>Statement date:</td><td>18 Feb 2026</td></tr>...</table>
            target_table_2 = tables[1].find_all('td', class_='regular')
            for i, td in enumerate(target_table_2):
                if "Statement date:" in td.get_text():
                    data['Pos_date'] = target_table_2[i+1].get_text(strip=True)
                    data['Pos_date'] = pd.to_datetime(data['Pos_date'], format="%d %b %Y").strftime("%Y-%m-%d")
            # 2. Account (第 3 個 table -> 第二個 tr)
            # 結構: <tr><td colspan="3">List of accounts... 21583</td></tr>
            target_td = soup.find('td', string=lambda x: x and "Consolidated report:" in x)
            if target_td:
                # 找到含有 "Consolidated report:" 的 td 隔壁的 td 區塊裡面的文字
                account_cell = target_td.find_parent('tr').find_all('td', class_='regular')
                nums = [td.get_text(strip=True) for td in account_cell if td.get_text(strip=True).isdigit()]
                if nums:
                    data['Account'] = nums[0]
            # 如果上面沒抓到，改抓 "List of accounts" 那一行
            if 'Account' not in data:
                account_line = soup.find('td', string=lambda x: x and "List of accounts" in x)
                if account_line:
                    text = account_line.get_text(strip=True)
                    data['Account'] = text.split()[-1]

            # 3. Holding 到 QLR (第 4 個 table -> 第 3 個 td 底下的內部 table)
            for tr in soup.find_all('tr'):
                text = tr.get_text(strip=True)
                if "Total Holding Value" in text:
                    raw_val = tr.find_all('td')[-1].get_text(strip=True)
                    data['Holding'] = clean_num(raw_val)
                elif "Total On Loan" in text:
                    raw_val = tr.find_all('td')[-1].get_text(strip=True)
                    data['Loan'] = clean_num(raw_val)
                elif "Total Borrowed" in text:
                    raw_val = tr.find_all('td')[-1].get_text(strip=True)
                    data['Borrowed'] = clean_num(raw_val)               
                elif "Total Pledged for Collateral" in text:
                    raw_val = tr.find_all('td')[-1].get_text(strip=True)
                    data['Pledged'] = clean_num(raw_val)   
                elif "Total Eligible Collateral Value" in text:
                    raw_val = tr.find_all('td')[-1].get_text(strip=True)
                    data['Collateral'] = clean_num(raw_val)
                elif "Total QLR" in text:
                    raw_val = tr.find_all('td')[-1].get_text(strip=True)
                    data['QLR'] = clean_num(raw_val)

        except Exception as e:
            print(f"解析檔案 {file_path} 時發生錯誤: {e}")
            
        return data

    htmls = Path(r"Y:\科組資料夾\風控企劃科\10 專案\專案-Clearstream保管業務\MT535").glob("*.html")
    all_records = []

    for html in htmls:
        result = parse_mt535_html(html)
        if result:
            all_records.append(result)

    df_final = pd.DataFrame(all_records)
    df_final.to_csv("test.csv", index=False)
    return df_final


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