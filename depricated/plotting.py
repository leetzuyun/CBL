import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import urllib
import urllib3
import shutil
import os
from sqlalchemy import create_engine
import requests
from datetime import datetime
import json

def generate_plots():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    def fetch_sinopac_rates():
        url = "https://mma.sinopac.com/ws/share/rate/ws_exchange.ashx?exchangeType=REMIT&Cross=genREMITResult"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mma.sinopac.com/"
        }
        
        rates = {"TWD": 1.0}
        fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        try:
            res = requests.get(url, headers=headers, timeout=10, verify=False)
            res.raise_for_status()
            raw_text = res.text.strip()
            start_idx = raw_text.find("(") + 1
            end_idx = raw_text.rfind(")")
            
            if start_idx > 0 and end_idx > start_idx:
                json_str = raw_text[start_idx:end_idx]
                data = json.loads(json_str)
                
                for item in data:
                    if data and "SubInfo" in data[0]:
                        exchange_list = data[0]["SubInfo"]
                        for item in exchange_list:
                            cur = item.get("DataValue4") 
                            rb_rate = item.get("DataValue2") 
                            if cur and rb_rate:
                                rates[cur.strip().upper()] = float(rb_rate)
                        print(f"✅ 成功解析 {len(rates)-1} 種外幣匯率")
                    
        except Exception as e:
            print(f"⚠️ 匯率處理失敗，將使用預設值。錯誤: {e}")
            rates.update({"USD": 32.0, "EUR": 34.5, "JPY": 0.22})
            fetch_time = "取得失敗 (解析錯誤)"
        return rates, fetch_time

    fx_rates, fx_fetch_time = fetch_sinopac_rates()

    # 換算為約當美金的輔助函數
    def to_usd(row, val_col, cur_col):
        val = row[val_col]
        cur = row[cur_col]
        
        if pd.isna(val) or pd.isna(cur):
            return 0.0
            
        cur = str(cur).upper()
        if cur == "USD":
            return val
            
        # (原幣別換回台幣) / (美金換成台幣) = 約當美金
        rate_cur = fx_rates.get(cur, 1.0)
        rate_usd = fx_rates.get("USD", 1.0)
        return val * (rate_cur / rate_usd)

    # 1. get data from SQL server
    params = urllib.parse.quote_plus(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=128.110.24.133;"
        "DATABASE=MIDOFFICE;"
        "TrustServerCertificate=yes;"
        "UID=fixuser;"
        "PWD=7ujm4rfv;"
    )
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

    query = "SELECT * FROM HST_ASL_D"
    df = pd.read_sql_query(query, engine)

    # 2. Data preprocessing
    df["Pos_date"] = pd.to_datetime(df["Pos_date"], errors="coerce")
    df["LoanQuantity"] = pd.to_numeric(df["LoanQuantity"], errors="coerce")
    df["AccruedCommission"] = pd.to_numeric(df["AccruedCommission"], errors="coerce")
    df["Month"] = df["Pos_date"].dt.to_period("M").astype(str)

    df["LoanQuantity_USD"] = df.apply(lambda x: to_usd(x, "LoanQuantity", "LoanValueCurrency"), axis=1)
    df["AccruedCommission_USD"] = df.apply(lambda x: to_usd(x, "AccruedCommission", "AccruedCommissionCurrency"), axis=1)

    months = sorted(df["Month"].unique())
    accounts = sorted(df["Account"].unique())

    # --- First plot: data prep for barchart ---
    daily_qty = df.groupby(["Pos_date", "ISIN", "SecurityName", "Month", "Account", "LoanValueCurrency"], as_index=False).agg(
        Daily_Loan_Quantity=("LoanQuantity", "sum"),
        Daily_Loan_Quantity_USD=("LoanQuantity_USD", "sum")
    )
    daily_acc = df[["Pos_date", "ISIN", "SecurityName", "AccruedCommission", "AccruedCommission_USD", "AccruedCommissionCurrency", "Month", "Account"]].dropna(subset=["AccruedCommission"]).sort_values(["ISIN", "Pos_date"])

    isins = sorted(daily_qty["ISIN"].unique())
    colors = px.colors.qualitative.Set2
    isin_color_map = {isin: colors[i % len(colors)] for i, isin in enumerate(isins)}

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    seen_isins_qty = set()
    seen_isins_acc = set()

    for m in months:
        for acc in accounts:
            for isin in isins:
                qty_sub = daily_qty[(daily_qty["ISIN"] == isin) & (daily_qty["Month"] == m) & (daily_qty["Account"] == acc)]
                acc_sub = daily_acc[(daily_acc["ISIN"] == isin) & (daily_acc["Month"] == m) & (daily_acc["Account"] == acc)]
                
                if not qty_sub.empty:
                    is_first_bar = isin not in seen_isins_qty
                    # trace_currency = str(qty_sub["LoanValueCurrency"].iloc[0]).upper()
                    # if trace_currency == "USD":
                    #     hover_temp_bar = (
                    #         "<b>原幣借出: %{customdata[2]:,.2f} USD</b>"
                    #         "<extra></extra>"
                    #     )
                    # else:
                    #     hover_temp_bar = (
                    #         "<b>約當美金: %{y:,.2f} USD</b><br>"
                    #         "原幣借出: %{customdata[2]:,.2f} %{customdata[3]}"
                    #         "<extra></extra>"
                    #     )
                    cd = list(zip(
                        [m] * len(qty_sub),
                        [acc] * len(qty_sub),
                        qty_sub["Daily_Loan_Quantity"],
                        qty_sub["LoanValueCurrency"]
                    ))
                    fig.add_trace(
                        go.Bar(
                            x=qty_sub["Pos_date"] + pd.Timedelta(hours=12), 
                            # y=qty_sub["Daily_Loan_Quantity_USD"], # 使用約當美金
                            y=qty_sub["Daily_Loan_Quantity"], # 顯示原幣借出量
                            name=f"{qty_sub['SecurityName'].iloc[0]}",
                            marker_color=isin_color_map[isin],
                            legendgroup="group_bar", 
                            legendgrouptitle=dict(text="借出量(原幣)"),
                            showlegend=is_first_bar,
                            customdata=cd,
                            hovertemplate=(
                                "借出量: %{customdata[2]:,.2f} %{customdata[3]}"
                                "<extra></extra>"
                            ),
                            visible=True
                        ),
                        secondary_y=False
                    )
                    seen_isins_qty.add(isin)
                
                if not acc_sub.empty:
                    is_first_scatter = isin not in seen_isins_acc
                    trace_acc_currency = str(acc_sub["AccruedCommissionCurrency"].iloc[0]).upper()
                    if trace_acc_currency == "USD":
                        hover_temp_scatter = (
                            "<b>原幣利息: %{customdata[2]:,.2f} USD</b>"
                            "<extra></extra>"
                        )
                    else:
                        hover_temp_scatter = (
                            "<b>約當利息: %{y:,.2f} USD</b><br>"
                            "原幣利息: %{customdata[2]:,.2f} %{customdata[3]}"
                            "<extra></extra>"
                        )
                    cd = list(zip(
                        [m] * len(acc_sub),
                        [acc] * len(acc_sub),
                        acc_sub["AccruedCommission"],
                        acc_sub["AccruedCommissionCurrency"]
                    ))
                    
                    fig.add_trace(
                        go.Scatter(
                            x=acc_sub["Pos_date"] + pd.Timedelta(hours=12), 
                            y=acc_sub["AccruedCommission_USD"], # 使用約當美金
                            mode="lines+markers",
                            name=f"{acc_sub['SecurityName'].iloc[0]}",
                            line=dict(color=isin_color_map[isin], dash='dot'),
                            legendgroup="group_scatter",
                            legendgrouptitle=dict(text="累計利息收入 (約當 USD)"),
                            showlegend=is_first_scatter,
                            customdata=cd,
                            hovertemplate=hover_temp_scatter,
                            visible=True
                        ),
                        secondary_y=True
                    )
                    seen_isins_acc.add(isin)

    # FX rate info
    used_currencies = set(df["LoanValueCurrency"].dropna().unique()).union(set(df["AccruedCommissionCurrency"].dropna().unique()))
    cross_rates = []
    for c in used_currencies:
        if c in fx_rates and c != "USD" and c != "TWD":
            cross_rate = fx_rates[c] / fx_rates["USD"]
            cross_rates.append(f"{c}/USD={cross_rate:.4f}")

    fx_note_str = "、".join(cross_rates) if cross_rates else "無外幣轉換"
    annotation_text = f"匯率基準 (即期匯款買入): {fx_note_str} | 取得時間: {fx_fetch_time}"

    fig.update_layout(
        barmode="stack",
        hovermode="x unified",
        height=650,
        margin=dict(l=50, r=50, t=80, b=140),
        xaxis=dict(
                type='date',
                tickformat="%m-%d",
                dtick=86400000.0,
                tick0="2000-01-01 00:00", 
                ticklabelmode="period",
                tickangle=0,
                automargin=True
            ),
        annotations=[
            dict(
                text=annotation_text,
                xref="paper", yref="paper",
                x=0.95, y=-0.1,  # 定位
                showarrow=False,
                xanchor="right",
                yanchor="top",
                font=dict(size=12, color="#666666"),
                # bgcolor="yellow"
            )
        ]
    )

    # --- Second plot: data prep for table ---
    all_tables_html = ""
    filter_months = months + ["全部"]
    filter_accounts = accounts + ["所有帳號"]

    for m in filter_months:
        for acc in filter_accounts:
            temp_df = df.copy()
            
            # 1. filter account
            if acc != "所有帳號":
                temp_df = temp_df[temp_df["Account"] == acc]
            # 2. filter month and calcualte commission
            if m != "全部":
                temp_df = temp_df[temp_df["Month"] == m]
                if not temp_df.empty:
                    month_table = (
                        temp_df.dropna(subset=["AccruedCommission_USD"])
                        .sort_values("Pos_date")
                        .groupby(["ISIN", "SecurityName", "Account", "AccruedCommissionCurrency"], as_index=False)
                        .last()
                    )
                else:
                    month_table = pd.DataFrame(columns=["ISIN", "SecurityName", "Account", "AccruedCommissionCurrency", "AccruedCommission", "AccruedCommission_USD"])
            else:
                if not temp_df.empty:
                    monthly_last = (
                        temp_df.dropna(subset=["AccruedCommission_USD"])
                        .sort_values("Pos_date")
                        .groupby(["Month", "ISIN", "SecurityName", "Account", "AccruedCommissionCurrency"], as_index=False)
                        .last()
                    )
                    month_table = (
                        monthly_last.groupby(["ISIN", "SecurityName", "Account", "AccruedCommissionCurrency"], as_index=False)
                        .agg({"AccruedCommission": "sum", "AccruedCommission_USD": "sum"})
                    )
                else:
                    month_table = pd.DataFrame(columns=["ISIN", "SecurityName", "Account", "AccruedCommissionCurrency", "AccruedCommission", "AccruedCommission_USD"])

            if not month_table.empty:
                month_table = month_table[["ISIN", "SecurityName", "Account", "AccruedCommissionCurrency", "AccruedCommission", "AccruedCommission_USD"]]
                month_table["AccruedCommission"] = month_table["AccruedCommission"].round(2)
                month_table["AccruedCommission_USD"] = month_table["AccruedCommission_USD"].round(2)
                month_table = month_table.sort_values("AccruedCommission_USD", ascending=False)
            
            header_usd = "利息加總 (約當 USD)" if m == "全部" else "當月累計利息 (約當 USD)"
            header_orig = "利息加總 (原幣)" if m == "全部" else "當月累計利息 (原幣)"
            
            table_html = month_table.to_html(
                index=False, 
                classes='display cell-border',
                border=0
            )
            table_html = table_html.replace('<th>AccruedCommission_USD</th>', f'<th>{header_usd}</th>')\
                                .replace('<th>AccruedCommission</th>', f'<th>{header_orig}</th>')\
                                .replace('<th>AccruedCommissionCurrency</th>', '<th>利息原幣幣別</th>')\
                                .replace('<th>SecurityName</th>', '<th>債券名稱</th>')\
                                .replace('<th>Account</th>', '<th>保管帳戶</th>')
            
            display_style = "display: block;" if (m == "全部" and acc == "所有帳號") else "display: none;"
            
            all_tables_html += f"""
            <div class="table-container" data-month="{m}" data-account="{acc}" style="{display_style}">
                <h4 style="margin: 10px 0; color: #666;">資料範圍: {m} | 帳號: {acc}</h4>
                {table_html}
            </div>
            """

    # --- Dropdown options for HTML ---
    html_account_options = '<option value="所有帳號">所有帳號</option>' + \
                        "".join([f'<option value="{acc}">{acc}</option>' for acc in accounts])

    html_month_options = '<option value="全部">全部月份</option>' + \
                        "".join([f'<option value="{m}">{m}</option>' for m in months])


    # --- HTML Template ---
    html_account_options = '<option value="所有帳號">所有帳號</option>' + \
                        "".join([f'<option value="{acc}">{acc}</option>' for acc in accounts])

    html_month_options = '<option value="全部">全部月份</option>' + \
                        "".join([f'<option value="{m}">{m}</option>' for m in months])

    html_template = f"""
    <html>
    <head>
        <meta charset="utf-8" />
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
        <style>
            body {{ font-family: sans-serif; margin: 30px; background-color: #f8f9fa; }}
            .section {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; }}
            .controls {{ display: flex; gap: 15px; margin-bottom: 15px; align-items: center; background: #f0f2f5; padding: 10px; border-radius: 4px; }}
            select {{ padding: 5px; border-radius: 4px; min-width: 150px; }}
            h2 {{ color: #333; border-left: 5px solid #007bff; padding-left: 10px; }}
            /* --- 數值欄位置右 --- */
            table.dataTable th:nth-child(5), 
            table.dataTable td:nth-child(5),
            table.dataTable th:nth-child(6), 
            table.dataTable td:nth-child(6) {{
                text-align: right !important;
            }}
            /* 讓表頭文字也置右對齊，並給予右方間距 */
            table.dataTable td:nth-child(5),
            table.dataTable td:nth-child(6) {{
                padding-right: 20px !important;
            }}
        </style>
    </head>
    <body>

        <div class="section">
            <h2>1. 各月債券日借出量與累計利息走勢</h2>
            <div class="controls">
                <strong>篩選圖表：</strong>
                帳號 <select id="chart-acc">{html_account_options}</select>
                月份 <select id="chart-month">{html_month_options}</select>
            </div>
            {fig.to_html(full_html=False, include_plotlyjs='cdn', div_id="plotly-chart")}
        </div>

        <div class="section">
            <h2>2. 各檔債券利息收入明細</h2>
            <div class="controls">
                <strong>篩選表格：</strong>
                帳號 <select id="table-acc">{html_account_options}</select>
                月份 <select id="table-month">{html_month_options}</select>
            </div>
            <div id="tables-wrapper">
                {all_tables_html}
            </div>
        </div>

        <script src="https://code.jquery.com/jquery-3.7.0.js"></script>
        <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
        <script>
        $(document).ready(function() {{
            // DataTables 預設依照最後一欄 約當USD 降冪
            $('table').DataTable({{ 
                paging: false, 
                searching: false, 
                info: false, 
                order: [[5, 'desc']] 
            }});

            function updateChart() {{
                var acc = $('#chart-acc').val();
                var month = $('#chart-month').val();
                var gd = document.getElementById('plotly-chart');
                
                if(!gd || !gd.data) return;

                var visibility = [];
                for (var i = 0; i < gd.data.length; i++) {{
                    var d = gd.data[i].customdata[0]; 
                    var mMatch = (month === "全部" || d[0] === month);
                    var aMatch = (acc === "所有帳號" || d[1] === acc);
                    visibility.push(mMatch && aMatch);
                }}

                Plotly.restyle(gd, {{ visible: visibility }});

                // 確保每個可見的 legend group 都至少保留一個 showlegend=true
                var showLegendUpdates = [];
                var firstVisibleLegendTrace = {{}};
                for (var i = 0; i < gd.data.length; i++) {{
                    if (!visibility[i]) continue;
                    var key = gd.data[i].name + '||' + (gd.data[i].legendgroup || '');
                    if (!(key in firstVisibleLegendTrace)) {{
                        firstVisibleLegendTrace[key] = i;
                    }}
                }}
                for (var i = 0; i < gd.data.length; i++) {{
                    var key = gd.data[i].name + '||' + (gd.data[i].legendgroup || '');
                    var shouldShowLegend = visibility[i] && firstVisibleLegendTrace[key] === i;
                    showLegendUpdates.push(shouldShowLegend);
                }}
                Plotly.restyle(gd, {{ showlegend: [showLegendUpdates] }});
                
                Plotly.relayout(gd, {{
                    'xaxis.type': 'date',
                    'yaxis.autorange': true,
                    'yaxis2.autorange': true
                }});
            }}

            function updateTable() {{
                var acc = $('#table-acc').val();
                var month = $('#table-month').val();
                
                $('.table-container').hide();
                var target = $('.table-container[data-month="' + month + '"][data-account="' + acc + '"]');
                target.show();
                
                if ($.fn.dataTable.isDataTable(target.find('table'))) {{
                    target.find('table').DataTable().columns.adjust();
                }}
            }}

            $('#chart-acc, #chart-month').on('change', updateChart);
            $('#table-acc, #table-month').on('change', updateTable);

            setTimeout(updateChart, 500); 
        }});
        </script>
    </body>
    </html>
    """

    filename = "CBL_Report.html"
    target_folder = r"Y:\科組資料夾\風控企劃科\10 專案\專案-Clearstream保管業務"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_template)
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
    target_path = os.path.join(target_folder, filename)
    shutil.copy2(filename, target_path)

    print("CBL_Report.html generated and saved to Public Folder.")

if __name__ == "__main__":
    generate_plots()