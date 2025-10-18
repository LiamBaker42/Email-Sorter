import email.utils

def extract_email_address(full: str) -> str:
    """
    Extracts the email address from a full 'From' string.
    Example: 'John Doe <john@example.com>' -> 'john@example.com'
    """
    return email.utils.parseaddr(full)[1]

def kb_from_size(size_bytes: int) -> float:
    """
    Converts bytes to kilobytes, rounded to one decimal.
    Returns 0 if size is None or invalid.
    """
    if size_bytes is None or not isinstance(size_bytes, int):
        return 0
    return round(size_bytes / 1024, 1)

from email.utils import parsedate_to_datetime

def parse_imap_date(date_str: str) -> str:
    """
    Parse an IMAP date string (from email headers) into
    a standardized ISO format string for display.
    Returns empty string if parsing fails.
    """
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%a, %d %b %Y %H:%M:%S")
    except Exception:
        return date_str
