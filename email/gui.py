# gui.py
import tkinter as tk
from tkinter import ttk, messagebox
from modern_widgets import ModernButton, ModernEntry, ModernLabel, ModernFrame, ModernTreeview, ModernScrollbar
from inbox_manager import InboxManager
from datetime import datetime, timedelta
import threading, math

class InboxCleanerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Inbox Cleaner")
        self.root.geometry("1200x700")

        self.manager = InboxManager(batch_size=50)
        self.manager.on_sender_list_updated = self.refresh_sender_list
        self.manager.on_email_list_updated = self.refresh_email_table
        self.manager.on_progress_update = self.update_progress
        self.manager.on_delete_progress = self.update_delete_progress

        self.search_var = tk.StringVar()
        self.sort_var = tk.StringVar(value="Count (desc)")
        self.batch_size_var = tk.IntVar(value=50)
        self.loading_label_var = tk.StringVar(value="")

        # Pagination
        self.current_page = 0
        self.emails_per_page = 50
        self.total_pages = 0

        # Deletion progress state
        self._delete_total = 0
        self._delete_done = 0

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        top_frame = ModernFrame(self.root)
        top_frame.pack(side="top", fill="x", padx=5, pady=5)

        ModernLabel(top_frame, text="IMAP Server:").pack(side="left")
        self.server_entry = ModernEntry(top_frame, width=25)
        self.server_entry.pack(side="left", padx=5)
        self.server_entry.entry.insert(0, "imap.gmail.com")

        ModernLabel(top_frame, text="Email:").pack(side="left")
        self.email_entry = ModernEntry(top_frame, width=25)
        self.email_entry.pack(side="left", padx=5)
        self.email_entry.entry.insert(0, "")

        ModernLabel(top_frame, text="App Password:").pack(side="left")
        self.password_entry = ModernEntry(top_frame, width=25)
        self.password_entry.pack(side="left", padx=5)
        self.password_entry.entry.insert(0, "")

        ModernLabel(top_frame, text="Batch Size:").pack(side="left", padx=(10, 0))
        self.batch_spin = tk.Spinbox(top_frame, from_=10, to=10000, increment=50,
                                     textvariable=self.batch_size_var, width=5)
        self.batch_spin.pack(side="left", padx=5)

        ModernButton(top_frame, text="Connect", command=self.connect_to_server).pack(side="left", padx=5)

        # Search/Sort frame
        search_frame = ModernFrame(self.root)
        search_frame.pack(side="top", fill="x", padx=5, pady=2)

        ModernLabel(search_frame, text="Search Sender:").pack(side="left")
        search_entry = ModernEntry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side="left", padx=5)
        search_entry.entry.bind("<KeyRelease>", lambda e: self.refresh_sender_list())

        ModernLabel(search_frame, text="Sort By:").pack(side="left", padx=(10,0))
        sort_combo_frame = ModernFrame(search_frame)
        sort_combo_frame.pack(side="left", padx=5)
        sort_combo = ttk.Combobox(sort_combo_frame, textvariable=self.sort_var,
                                  values=["Count (desc)", "Sender (asc)", "Latest Date"],
                                  state="readonly", width=20)
        sort_combo.pack(fill="both", expand=True)
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_sender_list())

        # Middle frame
        mid_frame = ModernFrame(self.root)
        mid_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)

        # Main horizontal paned window (Sender List | Email List & Preview)
        main_paned_window = ttk.PanedWindow(mid_frame, orient=tk.HORIZONTAL)
        main_paned_window.pack(fill="both", expand=True)

        # --- Left Pane: Sender Tree ---
        sender_frame = ModernFrame(main_paned_window)
        self.sender_tree = ModernTreeview(sender_frame, columns=("sender","count"), show="headings")
        self.sender_tree.heading("sender", text="Sender")
        self.sender_tree.heading("count", text="Count")
        self.sender_tree.pack(side="left", fill="both", expand=True)
        self.sender_tree.bind("<<TreeviewSelect>>", lambda e: self.refresh_email_table())
        sender_vscroll = ModernScrollbar(sender_frame, orient='vertical', command=self.sender_tree.yview)
        sender_hscroll = ModernScrollbar(sender_frame, orient='horizontal', command=self.sender_tree.xview)
        self.sender_tree.configure(yscrollcommand=sender_vscroll.set, xscrollcommand=sender_hscroll.set)
        sender_vscroll.pack(side='right', fill='y')
        sender_hscroll.pack(side='bottom', fill='x')
        main_paned_window.add(sender_frame, weight=1)

        # --- Right Pane: Vertical Paned Window (Email List / Preview) ---
        right_pane = ModernFrame(main_paned_window)
        main_paned_window.add(right_pane, weight=3)
        email_paned_window = ttk.PanedWindow(right_pane, orient=tk.VERTICAL)
        email_paned_window.pack(fill="both", expand=True)

        # --- Top part of Right Pane: Email Tree ---
        email_frame = ModernFrame(email_paned_window)
        self.email_tree = ModernTreeview(email_frame, columns=("subject","date","size"), show="headings")
        self.email_tree.heading("subject", text="Subject")
        self.email_tree.heading("date", text="Date")
        self.email_tree.heading("size", text="Size (KB)")
        self.email_tree.pack(side="left", fill="both", expand=True)
        # Bind selection to update the preview pane
        self.email_tree.bind("<<TreeviewSelect>>", self.update_preview_pane)
        # Keep double-click functionality if you still want to open in a new window
        self.email_tree.bind("<Double-1>", self.open_selected_email)
        email_vscroll = ModernScrollbar(email_frame, orient='vertical', command=self.email_tree.yview)
        email_hscroll = ModernScrollbar(email_frame, orient='horizontal', command=self.email_tree.xview)
        self.email_tree.configure(yscrollcommand=email_vscroll.set, xscrollcommand=email_hscroll.set)
        email_vscroll.pack(side='right', fill='y')
        email_hscroll.pack(side='bottom', fill='x')
        email_paned_window.add(email_frame, weight=2)

        # --- Bottom part of Right Pane: Preview Pane ---
        preview_frame = ModernFrame(email_paned_window, bg="white")
        email_paned_window.add(preview_frame, weight=3)
        self.preview_text = tk.Text(preview_frame, wrap="word", state="disabled", bd=0, font=("Helvetica", 11))
        self.preview_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        preview_scroll = ModernScrollbar(preview_frame, command=self.preview_text.yview)
        preview_scroll.pack(side="right", fill="y")
        self.preview_text.config(yscrollcommand=preview_scroll.set)

        # Bottom Frame
        bottom_frame = ModernFrame(self.root)
        bottom_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        self.progress = ttk.Progressbar(bottom_frame, orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=5)

        ModernButton(bottom_frame, text="Load Next Batch", command=self.load_batch_with_indicator).pack(side="left", padx=5)
        ModernButton(bottom_frame, text="Delete Selected", command=self.delete_selected_emails).pack(side="left", padx=5)
        ModernButton(bottom_frame, text="Delete All from Sender", command=self.delete_all_for_sender).pack(side="left", padx=5)
        self.loading_label = ModernLabel(bottom_frame, text="", textvariable=self.loading_label_var)
        self.loading_label.pack(side="left", padx=10)
        
    # ---------------- Display Update Callbacks ----------------
    def update_progress(self, current, maximum):
        # loading batch progress
        self.progress['maximum'] = maximum
        self.progress['value'] = current
        self.loading_label_var.set(f"Loading {current}/{maximum} emails...")

    def update_delete_progress(self, deleted_count, total_for_step):
        if self._delete_total <= 0:
            return
        self._delete_done += deleted_count
        self._delete_done = min(self._delete_done, self._delete_total)
        self.progress['maximum'] = self._delete_total
        self.progress['value'] = self._delete_done
        self.loading_label_var.set(f"Deleting {self._delete_done}/{self._delete_total} emails...")

        if self._delete_done >= self._delete_total:
            self._enable_ui()
            self.refresh_sender_list()
            self.refresh_email_table()

    def refresh_sender_list(self):
        self.sender_tree.delete(*self.sender_tree.get_children())
        senders = self.manager.get_senders(self.search_var.get(), self.sort_var.get())
        for sender in senders:
            self.sender_tree.insert("", "end", iid=sender['sender'], values=(sender['sender'], sender['count']))

    def refresh_email_table(self):
        # Clear preview pane when the list is refreshed
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.config(state="disabled")

        self.email_tree.delete(*self.email_tree.get_children())
        selected = self.sender_tree.selection()
        if not selected:
            return
        sender = selected[0]
        emails = self.manager.get_emails_for_sender(sender)
        for idx, item in enumerate(emails):
            uid_tag = f"uid_{item['uid_bytes']}"
            self.email_tree.insert("", "end", iid=item['uid'], values=(item['subject'], item['date'], item['size']), tags=(uid_tag,))
            try:
                email_date = datetime.strptime(item['date'][:25], "%a, %d %b %Y %H:%M:%S")
                if datetime.now() - email_date < timedelta(days=7):
                    self.email_tree.tag_configure(uid_tag, background="#FFF2CC")
            except Exception:
                pass

        # Alternate row colors
        for idx, child in enumerate(self.email_tree.get_children()):
            existing_tags = self.email_tree.item(child, 'tags')
            if isinstance(existing_tags, str):
                existing_tags = (existing_tags,)
            tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            self.email_tree.item(child, tags=existing_tags + (tag,))
        self.email_tree.tag_configure('oddrow', background="#ffffff")
        self.email_tree.tag_configure('evenrow', background="#e6f2ff")

    def update_preview_pane(self, event=None):
        selected_items = self.email_tree.selection()
        if not selected_items:
            return

        uid = selected_items[0]
        sender = self.sender_tree.selection()[0]

        emails = self.manager.get_emails_for_sender(sender)
        uid_bytes = None
        for item in emails:
            if item['uid'] == uid:
                uid_bytes = item['uid_bytes']
                break
        if not uid_bytes:
            return

        # Fetch and display the body in the preview pane
        body = self.manager.fetch_email_body(uid_bytes)
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", body)
        self.preview_text.config(state="disabled")

    # ---------------- Actions ----------------
    def connect_to_server(self):
        server = self.server_entry.entry.get()
        email_addr = self.email_entry.entry.get()
        password = self.password_entry.entry.get()
        batch_size = self.batch_size_var.get()

        if not all([server, email_addr, password]):
            messagebox.showerror("Error", "Please fill all fields")
            return

        self.manager.set_batch_size(batch_size)
        try:
            total = self.manager.connect(server, email_addr, password)
            messagebox.showinfo("Connected", f"Connected and fetched {total} email IDs\nBatch size = {batch_size}")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def load_batch_with_indicator(self):
        threading.Thread(target=self.manager.load_next_batch, daemon=True).start()

    def delete_selected_emails(self):
        selected_items = self.email_tree.selection()
        if not selected_items:
            return
        sender_selection = self.sender_tree.selection()
        if not sender_selection:
            return
        sender = sender_selection[0]

        uids_to_delete = [item_id for item_id in selected_items]

        def worker():
            self._delete_total = len(uids_to_delete)
            self._delete_done = 0
            self._disable_ui()
            self.manager.delete_emails(uids_to_delete, sender)

        threading.Thread(target=worker, daemon=True).start()

    def delete_all_for_sender(self):
        sender_selection = self.sender_tree.selection()
        if not sender_selection:
            return
        sender = sender_selection[0]

        emails = self.manager.get_emails_for_sender(sender)
        if not emails:
            messagebox.showinfo("No Emails", f"No emails loaded for {sender}")
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete all {len(emails)} loaded emails from {sender}?"
        )
        if not confirm:
            return

        uid_bytes_list = [item['uid_bytes'] for item in emails]
        display_uids = [item['uid'] for item in emails]
        total = len(uid_bytes_list)
        if total == 0:
            return

        chunk_size = 200
        chunks = [uid_bytes_list[i:i+chunk_size] for i in range(0, total, chunk_size)]

        self._delete_total = total
        self._delete_done = 0
        self._disable_ui()

        def worker_chunk(chunk):
            self.manager.delete_uids_bytes(chunk)

        max_threads = min(8, max(1, len(chunks)))
        chunk_queue = chunks.copy()
        queue_lock = threading.Lock()

        def thread_worker():
            while True:
                with queue_lock:
                    if not chunk_queue:
                        return
                    c = chunk_queue.pop()
                try:
                    worker_chunk(c)
                except Exception:
                    pass

        threads = []
        for _ in range(max_threads):
            t = threading.Thread(target=thread_worker, daemon=True)
            t.start()
            threads.append(t)

        def waiter():
            for t in threads:
                t.join()
            self.manager.grouped[sender] = [item for item in self.manager.get_emails_for_sender(sender) if item['uid'] not in display_uids]
            self._enable_ui()
            self.refresh_sender_list()
            self.refresh_email_table()

        threading.Thread(target=waiter, daemon=True).start()

    # ---------------- UI helpers ----------------
    def _disable_ui(self):
        try:
            for child in self.root.winfo_children():
                child.configure(state='disabled')
        except Exception:
            pass

    def _enable_ui(self):
        try:
            for child in self.root.winfo_children():
                child.configure(state='normal')
            self.loading_label_var.set("")
            self.progress['value'] = 0
            self.progress['maximum'] = 0
        except Exception:
            pass
    
    def open_selected_email(self, event=None):
        selected_items = self.email_tree.selection()
        if not selected_items:
            return

        uid = selected_items[0]
        sender = self.sender_tree.selection()[0]

        emails = self.manager.get_emails_for_sender(sender)
        uid_bytes = None
        for item in emails:
            if item['uid'] == uid:
                uid_bytes = item['uid_bytes']
                break
        if not uid_bytes:
            return

        body = self.manager.fetch_email_body(uid_bytes)

        win = tk.Toplevel(self.root)
        win.title("Email Content")
        text = tk.Text(win, wrap="word")
        text.insert("1.0", body)
        text.config(state="disabled")
        text.pack(fill="both", expand=True)