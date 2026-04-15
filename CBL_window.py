import tkinter as tk
from tkinter import ttk, messagebox

from lib import loan_data_processor, mt535_data_processor, plotting

class DataPipelineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CBL Data Pipeline v1.4")
        self.root.geometry("1100x650")
        
        self.filtered_df = None
        self.mt535_df = None
        self.setup_ui()

    def setup_ui(self):
        btn_frame = tk.Frame(self.root, pady=10)
        btn_frame.pack(fill=tk.X)

        # Loan 按鈕
        self.btn_get = tk.Button(btn_frame, text="1. Get Loan", command=self.get_loan_data, font=("Arial", 10), bg="#C7C1B1", fg="white")
        self.btn_get.pack(side=tk.LEFT, padx=5)

        self.btn_process = tk.Button(btn_frame, text="2. Process Loan", command=self.process_loan_data, font=("Arial", 10), bg="#C7C1B1", fg="white")
        self.btn_process.pack(side=tk.LEFT, padx=5)

        self.btn_upload = tk.Button(btn_frame, text="3. Upload Loan", command=self.upload_to_sql, font=("Arial", 10), bg="#C7C1B1", fg="white", state=tk.DISABLED)
        self.btn_upload.pack(side=tk.LEFT, padx=5)

        # MT535 按鈕
        self.btn_process_mt535 = tk.Button(btn_frame, text="1. Process MT535 (Manual)", command=self.process_mt535_data, font=("Arial", 10), bg="#8AA1B1", fg="white")
        self.btn_process_mt535.pack(side=tk.LEFT, padx=5)

        self.btn_upload_mt535 = tk.Button(btn_frame, text="2. Upload MT535 (Manual)", command=self.upload_mt535_data, font=("Arial", 10), bg="#8AA1B1", fg="white")
        self.btn_upload_mt535.pack(side=tk.LEFT, padx=5)
        
        self.lbl_status = tk.Label(btn_frame, text="準備就緒", font=("Arial", 10), fg="gray")
        self.lbl_status.pack(side=tk.RIGHT, padx=10)

        # --- 資料顯示 (Treeview) ---
        tree_frame = tk.Frame(self.root, height=300)
        tree_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=10)

        scroll_y = tk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scroll_x = tk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        
        self.tree = ttk.Treeview(tree_frame, yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.config(command=self.tree.yview)
        scroll_x.config(command=self.tree.xview)

        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # --- Generate Report ---
        report_frame = tk.Frame(self.root)
        report_frame.pack(fill=tk.X, padx=10, pady=5)

        self.btn_report = tk.Button(report_frame, text="Generate Loan Report", command=self.generate_report, font=("Arial", 12), bg="#C7C1B1", fg="white")
        self.btn_report.pack(side=tk.LEFT, padx=10)

    def display_dataframe(self, df):
        self.tree.delete(*self.tree.get_children())
        if df.empty:
            return
        self.tree["column"] = list(df.columns)
        self.tree["show"] = "headings"
        for col in self.tree["column"]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, minwidth=100)
        for _, row in df.iterrows():
            self.tree.insert("", "end", values=list(row))

    # --- 以下是呼叫外部模組的方法 ---

    def get_loan_data(self):
        try:
            count, df_files = loan_data_processor.get_loan_data()
            self.lbl_status.config(text=f"成功複製 {count} 筆資料", fg="green")
            self.display_dataframe(df_files)
        except Exception as e:
            messagebox.showerror("錯誤", str(e))

    def process_loan_data(self):
        try:
            self.filtered_df = loan_data_processor.process_loan_data()
            self.display_dataframe(self.filtered_df)
            
            self.btn_upload.config(state=tk.NORMAL)
            self.lbl_status.config(text=f"已處理 {len(self.filtered_df)} 筆資料，並刪除原始檔案", fg="black")
            messagebox.showinfo("處理完成", f"資料處理完畢！\n整裡出 {len(self.filtered_df)} 筆資料，請確認無誤後點擊上傳")
        except Exception as e:
            messagebox.showerror("錯誤", f"處理資料時發生錯誤:\n{str(e)}")

    def update_status(self, msg):
        self.lbl_status.config(text=msg, fg="blue")
        self.root.update()

    def upload_to_sql(self):
        try:
            success, duplicate, other = loan_data_processor.upload_to_sql(self.filtered_df, progress_callback=self.update_status)
            
            msg = f"上傳完畢！\n成功上傳：{success} 筆\n重複資料：{duplicate} 筆\n"
            if other > 0:
                msg += f"\n其他錯誤: {other} 筆(詳細資訊請查看終端機)"
                
            messagebox.showinfo("上傳結果", msg)
            self.lbl_status.config(text=f"上傳完畢：成功 {success} 筆，重複 {duplicate} 筆", fg="green")
            self.btn_upload.config(state=tk.DISABLED)
            
        except Exception as e:
            messagebox.showerror("錯誤", f"上傳資料時發生錯誤:\n{str(e)}")
            self.lbl_status.config(text="上傳失敗", fg="red")

    def process_mt535_data(self):
        try:
            self.lbl_status.config(text="正在解析 MT535，請稍候...", fg="blue")
            self.root.update()
                
            self.mt535_df = mt535_data_processor.process_MT535_html()
                
            self.display_dataframe(self.mt535_df)
            
            self.lbl_status.config(text=f"MT535 處理完成，共 {len(self.mt535_df)} 筆", fg="green")
            messagebox.showinfo("處理完成", f"MT535 資料處理完畢！\n共抓到 {len(self.mt535_df)} 筆資料，請確認無誤後點擊上傳")        
        except Exception as e:
            messagebox.showerror("錯誤", f"處理 MT535 時發生錯誤:\n{str(e)}")
            self.lbl_status.config(text="MT535 處理失敗", fg="red")

    def upload_mt535_data(self):
        try:
            if self.mt535_df is None or self.mt535_df.empty:
                messagebox.showwarning("警告", "請先點擊 'Process MT535' 處理資料！")
                return
            uploaded_count = mt535_data_processor.upload_mt535_to_sql(self.mt535_df, progress_callback=self.update_status)                
            messagebox.showinfo("上傳結果", f"MT535 上傳完畢！\n成功寫入資料庫：{uploaded_count} 筆 (已過濾重複項)")
            self.lbl_status.config(text=f"MT535 上傳成功 ({uploaded_count} 筆)", fg="green")
            # 清空暫存
            # self.mt535_df = None 
        except Exception as e:
            messagebox.showerror("錯誤", f"上傳 MT535 時發生錯誤:\n{str(e)}")
            self.lbl_status.config(text="MT535 上傳失敗", fg="red")

    def generate_report(self):
        self.lbl_status.config(text="報表產生中...", fg="blue")
        self.root.update_idletasks()
        
        try:
            plotting.generate_plots()
            messagebox.showinfo("成功", "報表已成功產生！")
            self.lbl_status.config(text="報表產生成功", fg="green")
        except Exception as e:
            messagebox.showerror("失敗", f"產生報表時發生錯誤：\n{str(e)}")
            self.lbl_status.config(text="報表產生失敗", fg="red")


if __name__ == "__main__":
    root = tk.Tk()
    app = DataPipelineApp(root)
    root.mainloop()
