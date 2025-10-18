import imaplib
import email
from email.header import decode_header
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

# Terminal console
console = Console()

class EmailClient:
    def __init__(self, server, username, password, mailbox="INBOX", per_page=20):
        self.server = server
        self.username = username
        self.password = password
        self.mailbox = mailbox
        self.per_page = per_page
        self.connection = None
        self.all_uids = []
        self.page = 0
        self.selected_email = None

    def connect(self):
        self.connection = imaplib.IMAP4_SSL(self.server)
        self.connection.login(self.username, self.password)
        self.connection.select(self.mailbox)
        self.refresh_uids()

    def refresh_uids(self):
        result, data = self.connection.search(None, "ALL")
        if result == "OK":
            self.all_uids = data[0].split()[::-1]  # newest first

    def fetch_page(self):
        start = self.page * self.per_page
        end = start + self.per_page
        uids = self.all_uids[start:end]
        emails = []
        for uid in uids:
            result, data = self.connection.fetch(uid, "(RFC822.HEADER)")
            if result != "OK":
                continue
            msg = email.message_from_bytes(data[0][1])
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8", errors="ignore")
            from_ = msg.get("From")
            emails.append((uid, subject, from_))
        return emails

    def display_page(self):
        table = Table(title=f"📨 Inbox Page {self.page+1}", show_lines=True)
        table.add_column("Index", style="cyan", justify="right")
        table.add_column("From", style="green")
        table.add_column("Subject", style="bold yellow")
        emails = self.fetch_page()
        for i, (uid, subject, from_) in enumerate(emails, start=1):
            table.add_row(str(i), from_, subject)
        console.print(table)

    def open_email(self, index):
        uids = self.all_uids[self.page*self.per_page:(self.page+1)*self.per_page]
        if index < 1 or index > len(uids):
            console.print("[red]Invalid email index[/red]")
            return
        uid = uids[index-1]
        result, data = self.connection.fetch(uid, "(RFC822)")
        if result != "OK":
            console.print("[red]Failed to fetch email[/red]")
            return
        msg = email.message_from_bytes(data[0][1])
        console.print(f"\n[bold cyan]From:[/bold cyan] {msg.get('From')}")
        console.print(f"[bold cyan]Subject:[/bold cyan] {msg.get('Subject')}")
        console.print(f"[bold cyan]Date:[/bold cyan] {msg.get('Date')}\n")
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors="ignore")
        console.print(body or "[italic]No text content[/italic]")

    def delete_email(self, index):
        uids = self.all_uids[self.page*self.per_page:(self.page+1)*self.per_page]
        if index < 1 or index > len(uids):
            console.print("[red]Invalid email index[/red]")
            return
        uid = uids[index-1]
        self.connection.store(uid, "+FLAGS", "\\Deleted")
        self.connection.expunge()
        console.print("[green]Email deleted successfully[/green]")
        self.refresh_uids()

    def delete_all_from_sender(self, index):
        uids = self.all_uids[self.page*self.per_page:(self.page+1)*self.per_page]
        if index < 1 or index > len(uids):
            console.print("[red]Invalid email index[/red]")
            return
        uid = uids[index-1]
        result, data = self.connection.fetch(uid, "(RFC822.HEADER)")
        msg = email.message_from_bytes(data[0][1])
        sender = msg.get("From")
        console.print(f"[yellow]Deleting all emails from {sender}...[/yellow]")
        result, data = self.connection.search(None, f'FROM "{sender}"')
        if result == "OK":
            for del_uid in data[0].split():
                self.connection.store(del_uid, "+FLAGS", "\\Deleted")
            self.connection.expunge()
            console.print("[green]All emails from sender deleted[/green]")
            self.refresh_uids()

    def run(self):
        self.display_page()
        while True:
            cmd = Prompt.ask("\n[bold blue]Command[/bold blue]",
                             choices=["open", "delete", "delete_all", "next", "prev", "quit"],
                             default="next")
            if cmd == "quit":
                break
            elif cmd == "next":
                self.page += 1
                self.display_page()
            elif cmd == "prev":
                if self.page > 0:
                    self.page -= 1
                self.display_page()
            elif cmd == "open":
                idx = int(Prompt.ask("Enter email index"))
                self.open_email(idx)
            elif cmd == "delete":
                idx = int(Prompt.ask("Enter email index"))
                self.delete_email(idx)
                self.display_page()
            elif cmd == "delete_all":
                idx = int(Prompt.ask("Enter email index"))
                self.delete_all_from_sender(idx)
                self.display_page()


if __name__ == "__main__":
    # Example: replace with your credentials
    client = EmailClient("imap.gmail.com", "holothewisewolf2@gmail.com", "ttta ugdb svtx jjue")
    client.connect()
    client.run()
