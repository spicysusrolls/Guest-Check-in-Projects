import tkinter as tk
import ttkbootstrap as ttk
from tkinter import messagebox, filedialog
import cv2
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import sqlite3
import logging
import json
import uuid
import csv
import tkfontawesome as fa

# --- Main Configuration ---
MAIN_DIR = os.getcwd() # Use current working directory for portability
FACE_PATH = os.path.join(MAIN_DIR, "faces")
if not os.path.exists(FACE_PATH):
    os.makedirs(FACE_PATH)
DRIVER_LICENSE_PATH = os.path.join(MAIN_DIR, "Driver License")
if not os.path.exists(DRIVER_LICENSE_PATH):
    os.makedirs(DRIVER_LICENSE_PATH)
LOG_PATH = os.path.join(MAIN_DIR, "logs")
if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)
CHECKIN_FILE = os.path.join(MAIN_DIR, "checkin_records.json")
BADGE_DB_PATH = os.path.join(MAIN_DIR, "badge_inventory.db")
SMTP_CONFIG_FILE = os.path.join(MAIN_DIR, "smtp_config.json")

def init_badge_db():
    conn = sqlite3.connect(BADGE_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            badge_number TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS visitor_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, company TEXT, badge_id TEXT,
            reason_of_visit TEXT, area TEXT, time_in TEXT, time_out TEXT,
            face_file TEXT, driver_license_file TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_badge_db()

LOG_FILENAME = os.path.join(LOG_PATH, "debug.log")
logging.basicConfig(
    filename=LOG_FILENAME, level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%m-%d-%Y %H-%M-%S'
)

class GuestCheckInApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        
        self.title("Guest Check-In System")
        self.geometry("900x950")
        
        self.load_smtp_config()

        self.records = []
        self.face_file = None
        self.driver_license_file = None
        self.visitor_policy_var = tk.IntVar()
        
        self.load_records()
        self.create_widgets()
        self.update_treeview()
        self.update_available_badges()

    def load_smtp_config(self):
        try:
            with open(SMTP_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                self.smtp_server = config.get("smtp_server", "smtp.gmail.com")
                self.smtp_port = config.get("smtp_port", 587)
                self.sender_email = config.get("sender_email", "")
                self.sender_password = config.get("sender_password", "")
        except (FileNotFoundError, json.JSONDecodeError):
            self.smtp_server = "smtp.gmail.com"
            self.smtp_port = 587
            self.sender_email = "your_email@example.com"
            self.sender_password = ""
            logging.warning("SMTP config file not found or invalid. Using defaults.")
    
    def save_records(self):
        try:
            with open(CHECKIN_FILE, 'w') as f:
                json.dump(self.records, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving records: {e}")

    def load_records(self):
        if not os.path.exists(CHECKIN_FILE): return
        try:
            with open(CHECKIN_FILE, 'r') as f:
                records = json.load(f)
                for record in records:
                    if 'id' not in record:
                        record['id'] = str(uuid.uuid4())
                self.records = records
                self.save_records()
        except Exception as e:
            logging.error(f"Error loading records: {e}")

    def create_widgets(self):
        self.icon_camera = fa.icon_to_image("camera", fill="#333", scale_to_height=16)
        self.icon_id_card = fa.icon_to_image("id-card", fill="#333", scale_to_height=16)
        self.icon_signin = fa.icon_to_image("sign-in-alt", fill="white", scale_to_height=16)
        self.icon_signout = fa.icon_to_image("sign-out-alt", fill="white", scale_to_height=16)
        self.icon_search = fa.icon_to_image("search", fill="#555", scale_to_height=12)
        self.icon_admin = fa.icon_to_image("user-cog", fill="#337ab7", scale_to_height=16)

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        header_label = ttk.Label(main_frame, text="Guest Check-In", font=("Helvetica", 22, "bold"), bootstyle="primary")
        header_label.pack(pady=(0, 20))

        input_frame = ttk.Labelframe(main_frame, text="Guest Details", padding=20)
        input_frame.pack(pady=10, fill="x")
        input_frame.columnconfigure(1, weight=1)

        # Create widgets with specific instance variables
        ttk.Label(input_frame, text="Name:").grid(row=0, column=0, padx=5, pady=10, sticky="e")
        self.entry_name = ttk.Entry(input_frame)
        self.entry_name.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        ttk.Label(input_frame, text="Company:").grid(row=1, column=0, padx=5, pady=10, sticky="e")
        self.entry_company = ttk.Entry(input_frame)
        self.entry_company.grid(row=1, column=1, padx=5, pady=10, sticky="ew")

        # MODIFIED: Label text changed to indicate badge is optional
        ttk.Label(input_frame, text="Badge ID (Optional):").grid(row=2, column=0, padx=5, pady=10, sticky="e")
        self.badge_combo = ttk.Combobox(input_frame, state="readonly")
        self.badge_combo.grid(row=2, column=1, padx=5, pady=10, sticky="ew")

        ttk.Label(input_frame, text="Reason of Visit:").grid(row=3, column=0, padx=5, pady=10, sticky="e")
        self.entry_reason = ttk.Entry(input_frame)
        self.entry_reason.grid(row=3, column=1, padx=5, pady=10, sticky="ew")

        ttk.Label(input_frame, text="Area:").grid(row=4, column=0, padx=5, pady=10, sticky="e")
        self.entry_area = ttk.Entry(input_frame)
        self.entry_area.grid(row=4, column=1, padx=5, pady=10, sticky="ew")
        
        self.visitor_policy_check = ttk.Checkbutton(
            main_frame, text="Sushic Kitchen Visitor Policy Signed?",
            variable=self.visitor_policy_var, bootstyle="primary")
        self.visitor_policy_check.pack(pady=15)

        button_capture_frame = ttk.Frame(main_frame)
        button_capture_frame.pack(pady=10)
        
        self.capture_button = ttk.Button(button_capture_frame, text=" Capture Face", image=self.icon_camera, compound="left", command=self.capture_face, bootstyle="secondary")
        self.capture_button.pack(side="left", padx=10, ipadx=5, ipady=5)
        self.capture_driver_license_button = ttk.Button(button_capture_frame, text=" Capture License", image=self.icon_id_card, compound="left", command=self.capture_driver_license, bootstyle="secondary")
        self.capture_driver_license_button.pack(side="left", padx=10, ipadx=5, ipady=5)
        
        self.check_in_button = ttk.Button(main_frame, text=" Check In", image=self.icon_signin, compound="left", command=self.check_in, bootstyle="success")
        self.check_in_button.pack(pady=20, ipadx=15, ipady=8)

        display_frame = ttk.Labelframe(main_frame, text="Currently Checked-in Guests", padding=20)
        display_frame.pack(pady=10, fill="both", expand=True)

        search_frame = ttk.Frame(display_frame)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text=" Search:", image=self.icon_search, compound="left").pack(side="left", padx=(0, 10))
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self.perform_search)
        
        cols = ("Name", "Company", "Time In", "Badge ID", "Area", "Reason of Visit")
        self.tree = ttk.Treeview(display_frame, columns=cols, show="headings", bootstyle="primary")
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.pack(pady=10, fill="both", expand=True)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10, fill="x", side="bottom")

        self.check_out_button = ttk.Button(button_frame, text=" Check Out Selected", image=self.icon_signout, compound="left", command=self.check_out, bootstyle="danger")
        self.check_out_button.pack(side="left")
        self.admin_button = ttk.Button(button_frame, text=" Admin", image=self.icon_admin, compound="left", command=self.admin_action, bootstyle="info-outline")
        self.admin_button.pack(side="right")
        
    def perform_search(self, event=None):
        search_term = self.search_entry.get().lower()
        if not search_term:
            filtered_records = self.records
        else:
            filtered_records = [r for r in self.records if search_term in r['name'].lower() or search_term in r.get('company', '').lower()]
        self.update_treeview(records_to_display=filtered_records)

    def update_treeview(self, records_to_display=None):
        self.tree.delete(*self.tree.get_children())
        records = records_to_display if records_to_display is not None else self.records
        for record in records:
            values = (record["name"], record.get("company", ""), record["time_in"], record["badge_id"], record.get("area", ""), record["reason_of_visit"])
            self.tree.insert("", "end", iid=record["id"], values=values)
            
    def update_available_badges(self):
        conn = sqlite3.connect(BADGE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT badge_number FROM badges ORDER BY category, badge_number")
        all_badges = [row[0] for row in c.fetchall()]
        conn.close()
        used_badges = [record["badge_id"] for record in self.records if record["badge_id"]]
        self.badge_combo['values'] = [b for b in all_badges if b not in used_badges]

    def capture_image(self, window_title, save_dir, file_prefix):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Error", "Could not open webcam.")
            return None
        messagebox.showinfo("Instructions", "Press 'c' to capture, 'q' to quit.")
        filename = None
        while True:
            ret, frame = cap.read()
            if not ret: break
            cv2.imshow(window_title, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('c'):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(save_dir, f"{file_prefix}_{ts}.png")
                cv2.imwrite(filename, frame)
                messagebox.showinfo("Success", "Image saved.")
                break
            elif key == ord('q'): break
        cap.release()
        cv2.destroyAllWindows()
        return filename

    def capture_face(self):
        self.face_file = self.capture_image("Face Capture", FACE_PATH, "face")

    def capture_driver_license(self):
        self.driver_license_file = self.capture_image("Driver License", DRIVER_LICENSE_PATH, "license")

    def check_in(self):
        name = self.entry_name.get().strip()
        badge_id = self.badge_combo.get().strip()
        reason = self.entry_reason.get().strip()
        
        # MODIFIED: Badge ID is no longer required for check-in
        if not all([name, reason]):
            messagebox.showwarning("Input Error", "Name and Reason of Visit are required.")
            return
        if not self.face_file or not self.driver_license_file:
            messagebox.showwarning("Capture Error", "Face and License must be captured.")
            return

        record = {
            "id": str(uuid.uuid4()),
            "name": name,
            "company": self.entry_company.get().strip(),
            "badge_id": badge_id,
            "reason_of_visit": reason,
            "area": self.entry_area.get().strip(),
            "time_in": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "face_file": self.face_file,
            "driver_license_file": self.driver_license_file
        }
        self.records.append(record)
        messagebox.showinfo("Success", f"Guest {name} checked in.")
        
        # Clear fields after check-in
        self.entry_name.delete(0, "end")
        self.entry_company.delete(0, "end")
        self.badge_combo.set("")
        self.entry_reason.delete(0, "end")
        self.entry_area.delete(0, "end")
        self.face_file, self.driver_license_file = None, None
        
        self.save_records()
        self.update_treeview()
        self.update_available_badges()

    def check_out(self):
        if not self.tree.selection():
            messagebox.showwarning("Selection Error", "Please select a guest to check out.")
            return
        
        record_id = self.tree.selection()[0]
        record_to_checkout = next((r for r in self.records if r["id"] == record_id), None)
        
        if record_to_checkout:
            time_out = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.log_to_history(record_to_checkout, time_out)
            self.records.remove(record_to_checkout)
            messagebox.showinfo("Success", f"Guest {record_to_checkout['name']} checked out.")
            self.save_records()
            self.update_treeview()
            self.update_available_badges()

    def log_to_history(self, record, time_out):
        try:
            conn = sqlite3.connect(BADGE_DB_PATH)
            c = conn.cursor()
            c.execute("""
                INSERT INTO visitor_history (name, company, badge_id, reason_of_visit, area, time_in, time_out, face_file, driver_license_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (record['name'], record.get('company'), record['badge_id'], record['reason_of_visit'], record.get('area'), record['time_in'], time_out, record['face_file'], record['driver_license_file']))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Failed to log to history: {e}")

    def admin_action(self):
        admin_window = ttk.Toplevel(self)
        admin_window.title("Admin Menu")
        admin_window.geometry("350x300")
        admin_window.transient(self)
        
        ttk.Label(admin_window, text="Admin Menu", font=("Helvetica", 16, "bold")).pack(pady=20)
        
        button_configs = [
            ("Badge Inventory", self.badge_inventory_window, "secondary"),
            ("SMTP Settings", self.open_smtp_settings, "secondary"),
            ("Export Visitor History (CSV)", self.export_history_to_csv, "primary"),
            ("Check Out All Guests", self.checkout_all_guests, "danger")
        ]
        for text, command, style in button_configs:
            ttk.Button(admin_window, text=text, command=command, bootstyle=style).pack(pady=8, padx=20, fill="x")

    def export_history_to_csv(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files", "*.csv")], title="Save Visitor History")
        if not filepath: return
        try:
            conn = sqlite3.connect(BADGE_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM visitor_history")
            rows = cursor.fetchall()
            headers = [d[0] for d in cursor.description]
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
            messagebox.showinfo("Success", f"History exported to\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Error", f"An error occurred: {e}")

    def checkout_all_guests(self):
        if not self.records:
            messagebox.showinfo("Info", "No guests are currently checked in.")
            return
        if messagebox.askyesno("Confirm", "Check out all currently active guests?"):
            time_out = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for record in list(self.records):
                self.log_to_history(record, time_out)
                self.records.remove(record)
            self.save_records()
            self.update_treeview()
            self.update_available_badges()
            messagebox.showinfo("Success", "All guests have been checked out.")

    def badge_inventory_window(self):
        self.inv_window = ttk.Toplevel(self)
        self.inv_window.title("Badge Inventory")
        self.inv_window.geometry("550x500")
        self.inv_window.transient(self)

        frame = ttk.Frame(self.inv_window, padding=15)
        frame.pack(fill="both", expand=True)

        input_frame = ttk.Labelframe(frame, text="Add New Badge", padding=15)
        input_frame.pack(fill="x", pady=10)
        
        ttk.Label(input_frame, text="Category:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.category_var = tk.StringVar()
        self.inv_category_combo = ttk.Combobox(input_frame, textvariable=self.category_var, 
                                           values=["Visitor", "Contractor", "Temporary"],
                                           state="readonly")
        self.inv_category_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.inv_category_combo.current(0)
        
        ttk.Label(input_frame, text="Badge Number:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.inv_badge_number_entry = ttk.Entry(input_frame)
        self.inv_badge_number_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        log_badge_button = ttk.Button(input_frame, text="Log Badge", command=self.log_badge, bootstyle="success")
        log_badge_button.grid(row=2, column=0, columnspan=2, pady=10)

        display_frame = ttk.Labelframe(frame, text="Existing Badges", padding=15)
        display_frame.pack(fill="both", expand=True, pady=10)

        self.badge_tree = ttk.Treeview(display_frame, columns=("ID", "Badge Number", "Category", "Created At"), show="headings", bootstyle="primary")
        self.badge_tree.heading("ID", text="ID")
        self.badge_tree.heading("Badge Number", text="Badge Number")
        self.badge_tree.heading("Category", text="Category")
        self.badge_tree.heading("Created At", text="Created At")
        self.badge_tree.pack(fill="both", expand=True)

        self.inv_category_combo.bind("<<ComboboxSelected>>", lambda e: self.update_badge_tree())

        self.badge_context_menu = tk.Menu(self.inv_window, tearoff=0)
        self.badge_context_menu.add_command(label="Delete Badge", command=self.delete_badge)
        self.badge_tree.bind("<Button-3>", self.show_badge_context_menu)

        self.update_badge_tree()

    def log_badge(self):
        badge_number = self.inv_badge_number_entry.get().strip()
        category = self.category_var.get()
        if not badge_number:
            messagebox.showwarning("Input Error", "Badge Number is required.", parent=self.inv_window)
            return

        try:
            conn = sqlite3.connect(BADGE_DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO badges (badge_number, category) VALUES (?, ?)", (badge_number, category))
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", "Badge logged successfully.", parent=self.inv_window)
            self.inv_badge_number_entry.delete(0, tk.END)
            self.update_badge_tree()
            self.update_available_badges()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "This badge number already exists.", parent=self.inv_window)
        except Exception as e:
            logging.error(f"Error logging badge: {e}")
            messagebox.showerror("Database Error", f"An error occurred: {e}", parent=self.inv_window)

    def update_badge_tree(self):
        category = self.category_var.get()
        self.badge_tree.delete(*self.badge_tree.get_children())
        try:
            conn = sqlite3.connect(BADGE_DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, badge_number, category, created_at FROM badges WHERE category = ? ORDER BY created_at DESC", (category,))
            for row in c.fetchall():
                self.badge_tree.insert("", "end", values=row)
            conn.close()
        except Exception as e:
            logging.error(f"Error fetching badges: {e}")

    def show_badge_context_menu(self, event):
        row_id = self.badge_tree.identify_row(event.y)
        if row_id:
            self.badge_tree.selection_set(row_id)
            self.badge_context_menu.tk_popup(event.x_root, event.y_root)

    def delete_badge(self):
        selected_item = self.badge_tree.selection()
        if not selected_item:
            return
        
        badge_id = self.badge_tree.item(selected_item, "values")[0]
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this badge?", parent=self.inv_window):
            try:
                conn = sqlite3.connect(BADGE_DB_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM badges WHERE id = ?", (badge_id,))
                conn.commit()
                conn.close()
                self.update_badge_tree()
                self.update_available_badges()
            except Exception as e:
                logging.error(f"Error deleting badge: {e}")
                messagebox.showerror("Database Error", "Failed to delete badge.", parent=self.inv_window)

    def open_smtp_settings(self):
        self.smtp_window = ttk.Toplevel(self)
        self.smtp_window.title("SMTP Settings")
        self.smtp_window.geometry("450x300")
        self.smtp_window.transient(self)

        frame = ttk.Frame(self.smtp_window, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Configure SMTP Server", font=("Helvetica", 14)).pack(pady=10)

        form_frame = ttk.Frame(frame)
        form_frame.pack(fill="x", expand=True)
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="SMTP Server:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.smtp_server_entry = ttk.Entry(form_frame)
        self.smtp_server_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.smtp_server_entry.insert(0, self.smtp_server)

        ttk.Label(form_frame, text="Port:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.smtp_port_entry = ttk.Entry(form_frame)
        self.smtp_port_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.smtp_port_entry.insert(0, self.smtp_port)

        ttk.Label(form_frame, text="Sender Email:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.sender_email_entry = ttk.Entry(form_frame)
        self.sender_email_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.sender_email_entry.insert(0, self.sender_email)

        ttk.Label(form_frame, text="Password:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.sender_password_entry = ttk.Entry(form_frame, show="*")
        self.sender_password_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        self.sender_password_entry.insert(0, self.sender_password)

        update_btn = ttk.Button(frame, text="Save Settings", command=self.update_smtp_settings, bootstyle="primary")
        update_btn.pack(pady=20)

    def update_smtp_settings(self):
        self.smtp_server = self.smtp_server_entry.get().strip()
        self.smtp_port = int(self.smtp_port_entry.get().strip())
        self.sender_email = self.sender_email_entry.get().strip()
        self.sender_password = self.sender_password_entry.get().strip()
        
        config = {
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "sender_email": self.sender_email,
            "sender_password": self.sender_password
        }
        try:
            with open(SMTP_CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            messagebox.showinfo("Success", "SMTP settings saved successfully.", parent=self.smtp_window)
            self.smtp_window.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save SMTP settings: {e}", parent=self.smtp_window)


if __name__ == "__main__":
    app = GuestCheckInApp()
    app.mainloop()