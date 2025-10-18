import imaplib
import threading
from typing import List, Dict, Tuple
import email
from email.header import decode_header
from datetime import datetime, timedelta
from utils import extract_email_address, kb_from_size


def decode_header_value(raw: str) -> str:
    """Decode MIME-encoded headers, including emoji in subject lines."""
    if not raw:
        return ""
    try:
        dh = decode_header(raw)
        parts = []
        for text, enc in dh:
            if isinstance(text, bytes):
                try:
                    parts.append(text.decode(enc or "utf-8", errors="replace"))
                except Exception:
                    parts.append(text.decode("utf-8", errors="replace"))
            else:
                parts.append(text)
        return "".join(parts)
    except Exception:
        return raw


class InboxManager:
    """Unified class for IMAP connection, fetching, batch handling, and deleting."""

    def __init__(self, batch_size: int = 50):
        self.server: str = ""
        self.email_address: str = ""
        self.password: str = ""
        self.folder: str = "INBOX"
        self.conn: imaplib.IMAP4_SSL = None
        self.lock = threading.Lock()
        self.batch_size = batch_size

        # State
        self.all_uids: List[bytes] = []
        self.loaded_uids: List[bytes] = []
        self.grouped: Dict[str, List[Dict]] = {}
        self.sender_latest_date: Dict[str, str] = {}
        self.loading = False

        # GUI callbacks
        self.on_progress_update = None
        self.on_sender_list_updated = None
        self.on_email_list_updated = None
        self.on_batch_loaded = None

    # ---------------- Connection ----------------
    def connect(self, server: str, email_addr: str, password: str, folder="INBOX"):
        self.server = server
        self.email_address = email_addr
        self.password = password
        self.folder = folder

        self.conn = imaplib.IMAP4_SSL(self.server)
        self.conn.login(self.email_address, self.password)
        self.conn.select(self.folder)
        self.all_uids = self.fetch_email_ids()
        return len(self.all_uids)

    def set_batch_size(self, size: int):
        if size > 0:
            self.batch_size = size

    # ---------------- Fetching ----------------
    def fetch_email_ids(self) -> List[bytes]:
        status, messages = self.conn.search(None, "ALL")
        if status != "OK":
            return []
        return messages[0].split()[::-1]  # newest first

    def fetch_headers_batch(self, uids: List[bytes]) -> List[Tuple[bytes, Dict[str, str]]]:
        records = []
        for uid in uids:
            status, msg = self.conn.fetch(uid, "(RFC822.SIZE BODY[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK":
                continue
            for part in msg:
                if isinstance(part, tuple):
                    raw = part[1]
                    msg_obj = email.message_from_bytes(raw)
                    size = 0
                    for resp in msg:
                        if isinstance(resp, tuple) and b"RFC822.SIZE" in resp[0]:
                            try:
                                size = int(resp[0].split()[2])
                            except Exception:
                                size = 0
                    records.append((uid, {
                        "from": decode_header_value(msg_obj.get("From", "")),
                        "subject": decode_header_value(msg_obj.get("Subject", "")),
                        "date": msg_obj.get("Date", ""),
                        "size": size
                    }))
        return records

    # ---------------- Batch Handling ----------------
    def load_next_batch(self):
        if not self.conn or self.loading:
            return
        self.loading = True

        remaining = [u for u in self.all_uids if u not in set(self.loaded_uids)]
        batch = remaining[:self.batch_size]
        if not batch:
            self.loading = False
            return

        loaded_items = []
        for idx, (uid, rec) in enumerate(self.fetch_headers_batch(batch)):
            sender_addr = extract_email_address(rec.get('from', 'Unknown')) or 'Unknown'

            size_val = rec.get('size', None)
            if isinstance(size_val, int):
                size_kb = kb_from_size(size_val)
            elif isinstance(size_val, str) and size_val.isdigit():
                size_kb = kb_from_size(int(size_val))
            else:
                size_kb = kb_from_size(None)

            item = {
                'uid': uid.decode() if isinstance(uid, bytes) else str(uid),
                'subject': rec.get('subject', ''),
                'date': rec.get('date', ''),
                'size': size_kb,
                'sender': sender_addr
            }

            self.grouped.setdefault(sender_addr, []).append(item)
            cur = self.sender_latest_date.get(sender_addr, '')
            if item['date'] > cur:
                self.sender_latest_date[sender_addr] = item['date']

            loaded_items.append(item)
            if self.on_progress_update:
                self.on_progress_update(idx + 1, len(batch))

        self.loaded_uids.extend([uid for uid, _ in self.fetch_headers_batch(batch)])

        self.loading = False
        if self.on_batch_loaded:
            self.on_batch_loaded(loaded_items)
        if self.on_sender_list_updated:
            self.on_sender_list_updated()

    # ---------------- Utility ----------------
    def get_senders(self, search: str = '', sort_method: str = 'Count (desc)') -> List[Dict]:
        filtered = {s: emails for s, emails in self.grouped.items() if search.lower() in s.lower()}
        if sort_method == "Count (desc)":
            sorted_senders = sorted(filtered.items(), key=lambda x: len(x[1]), reverse=True)
        elif sort_method == "Sender (asc)":
            sorted_senders = sorted(filtered.items(), key=lambda x: x[0].lower())
        elif sort_method == "Latest Date":
            sorted_senders = sorted(filtered.items(),
                                    key=lambda x: self.sender_latest_date.get(x[0], ""),
                                    reverse=True)
        else:
            sorted_senders = filtered.items()
        return [{'sender': sender, 'count': len(emails)} for sender, emails in sorted_senders]

    def get_emails_for_sender(self, sender: str) -> List[Dict]:
        return self.grouped.get(sender, [])

    # ---------------- Deletion ----------------
    def delete_emails(self, uids: List[str], sender: str):
        if not uids:
            return
        with self.lock:
            for uid in uids:
                try:
                    self.conn.uid('COPY', uid.encode(), '[Gmail]/Trash')
                    self.conn.uid('STORE', uid.encode(), '+FLAGS', '(\\Deleted)')
                except Exception as e:
                    print(f"Failed to move UID {uid}: {e}")
            self.conn.expunge()

        self.grouped[sender] = [item for item in self.grouped[sender] if item['uid'] not in uids]
        if self.on_email_list_updated:
            self.on_email_list_updated()
        if self.on_sender_list_updated:
            self.on_sender_list_updated()
