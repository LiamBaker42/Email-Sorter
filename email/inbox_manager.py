# inbox_manager.py
import imaplib
import threading
from typing import List, Dict, Tuple
import email
from email.header import decode_header
import re
from utils import extract_email_address, kb_from_size, parse_imap_date

def decode_header_value(raw: str) -> str:
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
    def __init__(self, batch_size: int = 50):
        self.server = ""
        self.email_address = ""
        self.password = ""
        self.folder = "INBOX"
        self.conn: imaplib.IMAP4_SSL = None
        self.lock = threading.Lock()
        self.batch_size = batch_size

        # State
        self.all_uids: List[bytes] = []
        self.loaded_uids: List[bytes] = []
        self.grouped: Dict[str, List[Dict]] = {}
        self.sender_latest_date: Dict[str, str] = {}
        self.loading = False

        # Callbacks
        self.on_progress_update = None         # called while loading a batch: (current, total)
        self.on_sender_list_updated = None
        self.on_email_list_updated = None
        self.on_batch_loaded = None
        self.on_delete_progress = None         # new: called while deleting: (deleted_count, total_to_delete)

    # ---------------- Connection ----------------
    def connect(self, server: str, email_addr: str, password: str, folder="INBOX"):
        self.server = server
        self.email_address = email_addr
        self.password = password
        self.folder = folder

        self.conn = imaplib.IMAP4_SSL(self.server)
        self.conn.login(self.email_address, self.password)
        self.conn.select(self.folder)
        self.all_uids = self.uid_search_all()
        return len(self.all_uids)

    def set_batch_size(self, size: int):
        if size > 0:
            self.batch_size = size

    # ---------------- Fetching ----------------
    def uid_search_all(self) -> List[bytes]:
        with self.lock:
            typ, data = self.conn.uid('search', None, 'ALL')
        if typ != 'OK' or not data or not data[0]:
            return []
        return data[0].split()[::-1]  # newest first

    def fetch_headers_batch(self, uids: List[bytes], chunk_size: int = 200) -> List[Tuple[bytes, Dict[str, str]]]:
        """
        Threaded fetch of headers for large batches. Returns list of (uid_bytes, rec).
        """
        if not uids:
            return []

        results: List[Tuple[bytes, Dict[str, str]]] = []
        results_lock = threading.Lock()

        def fetch_chunk(chunk_uids: List[bytes]):
            try:
                uid_sequence = b','.join(chunk_uids)
                with self.lock:
                    typ, data = self.conn.uid(
                        'fetch',
                        uid_sequence,
                        '(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])'
                    )
                if typ != 'OK' or not data:
                    return

                current_uid = None
                hdr_bytes = b""
                size = None

                for part in data:
                    if isinstance(part, tuple):
                        meta, body = part
                        if isinstance(meta, bytes):
                            m = re.search(br'UID (\d+)', meta)
                            if m:
                                if current_uid is not None:
                                    msg = email.message_from_bytes(hdr_bytes)
                                    rec = {
                                        'from': decode_header_value(msg.get('From', '')),
                                        'subject': decode_header_value(msg.get('Subject', '')) or '(no subject)',
                                        'date': parse_imap_date(msg.get('Date', '')),
                                        'size': str(size or '')
                                    }
                                    with results_lock:
                                        results.append((current_uid.encode(), rec))
                                    hdr_bytes = b""
                                    size = None
                                current_uid = m.group(1).decode()
                            msize = re.search(br'RFC822\.SIZE (\d+)', meta)
                            if msize:
                                size = int(msize.group(1))
                        hdr_bytes += body or b""

                if current_uid is not None and hdr_bytes:
                    msg = email.message_from_bytes(hdr_bytes)
                    rec = {
                        'from': decode_header_value(msg.get('From', '')),
                        'subject': decode_header_value(msg.get('Subject', '')) or '(no subject)',
                        'date': parse_imap_date(msg.get('Date', '')),
                        'size': str(size or '')
                    }
                    with results_lock:
                        results.append((current_uid.encode(), rec))
            except Exception:
                return

        # Split UIDs into chunks and spawn threads
        chunks = [uids[i:i+chunk_size] for i in range(0, len(uids), chunk_size)]
        threads = []
        for chunk in chunks:
            t = threading.Thread(target=fetch_chunk, args=(chunk,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        return results

    # ---------------- Batch Handling ----------------
    def load_next_batch(self):
        if not self.conn or self.loading:
            return
        self.loading = True
        try:
            remaining = [u for u in self.all_uids if u not in set(self.loaded_uids)]
            batch = remaining[:self.batch_size]
            if not batch:
                return

            loaded_items = []
            records = self.fetch_headers_batch(batch)
            for idx, (uid, rec) in enumerate(records):
                sender_addr = extract_email_address(rec.get('from', 'Unknown')) or 'Unknown'
                size_val = rec.get('size', None)
                if isinstance(size_val, int):
                    size_kb = kb_from_size(size_val)
                elif isinstance(size_val, str) and size_val.isdigit():
                    size_kb = kb_from_size(int(size_val))
                else:
                    size_kb = kb_from_size(None)

                item = {
                    'uid_bytes': uid,                 # bytes internally
                    'uid': uid.decode(errors="replace"),  # string for GUI
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

            self.loaded_uids.extend([uid for uid, _ in records])

            if self.on_batch_loaded:
                self.on_batch_loaded(loaded_items)
            if self.on_sender_list_updated:
                self.on_sender_list_updated()
        finally:
            self.loading = False

    # ---------------- Utility ----------------
    def get_senders(self, search: str = '', sort_method: str = 'Count (desc)') -> List[Dict]:
        filtered_keys = [s for s in self.grouped.keys() if search.lower() in s.lower()]
        sender_info = [
            {'sender': s, 'count': len(self.grouped[s]), 'latest': self.sender_latest_date.get(s, '')}
            for s in filtered_keys
        ]
        if sort_method == 'Count (desc)':
            sender_info.sort(key=lambda x: x['count'], reverse=True)
        elif sort_method == 'Sender (asc)':
            sender_info.sort(key=lambda x: x['sender'].lower())
        elif sort_method == 'Latest Date':
            sender_info.sort(key=lambda x: x['latest'], reverse=True)
        return [{'sender': s['sender'], 'count': s['count']} for s in sender_info]

    def get_emails_for_sender(self, sender: str) -> List[Dict]:
        return self.grouped.get(sender, [])

    # ---------------- Deletion ----------------
    def delete_uids_bytes(self, uids_bytes: List[bytes], gmail_move_to_trash: bool = False) -> int:
        """
        Delete (MOVE to Trash) a list of UID bytes in one IMAP UID MOVE command.
        Returns number of UIDs successfully moved (best-effort).
        """
        if not uids_bytes:
            return 0

        moved = 0
        # Create a single comma-separated bytes sequence for the chunk
        uid_sequence = b','.join(uids_bytes)

        with self.lock:
            # Optionally copy to Bin first for best-effort safety
            if gmail_move_to_trash:
                try:
                    self.conn.uid('copy', uid_sequence, '"[Gmail]/Bin"')
                except Exception:
                    pass
            try:
                status, resp = self.conn.uid('move', uid_sequence, '[Gmail]/Trash')
                if status == 'OK':
                    moved = len(uids_bytes)
                else:
                    # If the server rejected the multi-UID MOVE, try individual moves
                    for uid in uids_bytes:
                        try:
                            s, _ = self.conn.uid('move', uid, '[Gmail]/Trash')
                            if s == 'OK':
                                moved += 1
                        except Exception:
                            continue
                try:
                    self.conn.expunge()
                except Exception:
                    pass
            except Exception:
                # Last resort: try per-UID move to maximize deletions
                for uid in uids_bytes:
                    try:
                        s, _ = self.conn.uid('move', uid, '[Gmail]/Trash')
                        if s == 'OK':
                            moved += 1
                    except Exception:
                        continue

        # report progress callback if present
        if self.on_delete_progress:
            try:
                self.on_delete_progress(moved, len(uids_bytes))
            except Exception:
                pass

        return moved

    def delete_emails(self, display_uids: List[str], sender: str, gmail_move_to_trash: bool = False):
        """
        Delete by display UIDs (strings) for a given sender. This collects the corresponding
        uid_bytes and calls delete_uids_bytes in chunked fashion for efficiency.
        """
        if not display_uids:
            return

        # Map display strings to uid_bytes
        uids_to_delete = [item['uid_bytes'] for item in self.grouped.get(sender, []) if item['uid'] in display_uids]
        if not uids_to_delete:
            return

        # Choose a chunk size for MOVE commands (adjustable)
        chunk_size = 200
        total = len(uids_to_delete)
        deleted_total = 0

        for i in range(0, total, chunk_size):
            chunk = uids_to_delete[i:i+chunk_size]
            moved = self.delete_uids_bytes(chunk, gmail_move_to_trash=gmail_move_to_trash)
            deleted_total += moved
            # report cumulative progress
            if self.on_delete_progress:
                try:
                    self.on_delete_progress(deleted_total, total)
                except Exception:
                    pass

        # Remove from internal storage
        self.grouped[sender] = [item for item in self.grouped.get(sender, []) if item['uid'] not in display_uids]
        if self.on_email_list_updated:
            self.on_email_list_updated()
        if self.on_sender_list_updated:
            self.on_sender_list_updated()

    from bs4 import BeautifulSoup

    def fetch_email_body(self, uid_bytes: bytes) -> str:
        try:
            with self.lock:
                typ, data = self.conn.uid("fetch", uid_bytes, "(RFC822)")
            if typ != "OK" or not data or not data[0]:
                return "[Could not fetch email]"

            msg = email.message_from_bytes(data[0][1])

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype == "text/plain":
                        body += part.get_payload(decode=True).decode(errors="replace")
                    elif ctype == "text/html" and not body:
                        html = part.get_payload(decode=True).decode(errors="replace")
                        soup = BeautifulSoup(html, "html.parser")
                        body += soup.get_text()
            else:
                if msg.get_content_type() == "text/plain":
                    body = msg.get_payload(decode=True).decode(errors="replace")
                elif msg.get_content_type() == "text/html":
                    html = msg.get_payload(decode=True).decode(errors="replace")
                    soup = BeautifulSoup(html, "html.parser")
                    body = soup.get_text()
            return body or "[No text content found]"
        except Exception as e:
            return f"[Error fetching email: {e}]"

