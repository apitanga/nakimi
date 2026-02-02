"""
Nakimi - Secure, just-in-time access to API credentials

A plugin-based vault for managing API credentials with age encryption.
"""

__version__ = "2.0.0"
__author__ = "Andre Pitanga"
__license__ = "MIT"

# Core
from .core import Vault, VaultConfig, get_config
from .core.plugin import Plugin, PluginManager, PluginError

# Plugins are imported from their subpackages
# from .plugins.gmail import GmailPlugin

__all__ = [
    "Vault",
    "VaultConfig",
    "get_config",
    "Plugin",
    "PluginManager",
    "PluginError",
]
