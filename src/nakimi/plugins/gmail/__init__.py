"""Gmail plugin for Nakimi"""

from .plugin import GmailPlugin
from .client import GmailClient, GmailAuthError

__all__ = ["GmailPlugin", "GmailClient", "GmailAuthError"]
