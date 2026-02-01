"""
Plugin system for Kimi Vault.

Plugins provide integration with specific services (Gmail, Calendar, etc.).
Each plugin is self-contained with its own client and CLI commands.
"""

import abc
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass


class PluginError(Exception):
    """Raised when plugin operations fail"""
    pass


@dataclass
class PluginCommand:
    """Represents a CLI command provided by a plugin"""
    name: str
    description: str
    handler: Callable[..., Any]
    args: List[tuple]  # List of (name, help, required) tuples


class Plugin(abc.ABC):
    """
    Base class for Kimi Vault plugins.
    
    Each plugin provides:
    - A service name (e.g., "gmail", "calendar")
    - Methods to interact with the service
    - CLI commands exposed through the main CLI
    
    Example:
        class GmailPlugin(Plugin):
            @property
            def name(self) -> str:
                return "gmail"
            
            def get_commands(self) -> List[PluginCommand]:
                return [
                    PluginCommand("unread", "List unread emails", self.list_unread, [])
                ]
    """
    
    def __init__(self, secrets: Dict[str, Any]):
        """
        Initialize plugin with decrypted secrets.
        
        Args:
            secrets: The plugin's section from the decrypted secrets.json
                     (e.g., for Gmail plugin, this is secrets["gmail"])
        """
        self.secrets = secrets
        self._validate_secrets()
    
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return the plugin name (e.g., 'gmail', 'calendar')"""
        pass
    
    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Return a short description of the plugin"""
        pass
    
    @abc.abstractmethod
    def _validate_secrets(self):
        """
        Validate that required secrets are present.
        
        Raises PluginError if required secrets are missing.
        """
        pass
    
    @abc.abstractmethod
    def get_commands(self) -> List[PluginCommand]:
        """
        Return list of CLI commands this plugin provides.
        
        Returns:
            List of PluginCommand objects
        """
        pass
    
    def health_check(self) -> tuple[bool, str]:
        """
        Check if the plugin is properly configured and can connect.
        
        Returns:
            Tuple of (is_healthy, message)
        """
        return True, "OK"


class PluginManager:
    """
    Manages plugin discovery, loading, and execution.
    """
    
    def __init__(self, secrets_data: Optional[Dict[str, Any]] = None):
        """
        Initialize plugin manager.
        
        Args:
            secrets_data: Full decrypted secrets dictionary
        """
        self.secrets_data = secrets_data or {}
        self._plugins: Dict[str, Plugin] = {}
        self._commands: Dict[str, tuple[str, PluginCommand]] = {}  # full_name -> (plugin_name, command)
    
    def register_plugin(self, plugin_class: type[Plugin], plugin_secrets: Optional[Dict] = None):
        """
        Register and instantiate a plugin.
        
        Args:
            plugin_class: The Plugin subclass to register
            plugin_secrets: Optional override for plugin secrets
        """
        plugin_name = plugin_class({}).name  # Get name without instantiating
        
        # Get secrets for this plugin
        if plugin_secrets is not None:
            secrets = plugin_secrets
        else:
            secrets = self.secrets_data.get(plugin_name, {})
        
        # Skip if no secrets (plugin not configured)
        if not secrets:
            return
        
        try:
            plugin = plugin_class(secrets)
            self._plugins[plugin_name] = plugin
            
            # Register commands
            for cmd in plugin.get_commands():
                full_name = f"{plugin_name}.{cmd.name}"
                self._commands[full_name] = (plugin_name, cmd)
                
        except PluginError as e:
            # Plugin failed to initialize (e.g., missing secrets)
            print(f"Warning: Plugin '{plugin_name}' not loaded: {e}", file=sys.stderr)
    
    def discover_plugins(self):
        """
        Auto-discover and register plugins from the plugins directory.
        
        Plugins are loaded if they have corresponding secrets in the vault.
        """
        from importlib import import_module
        
        # Get the plugins directory
        import kimi_vault.plugins as plugins_pkg
        plugins_dir = Path(plugins_pkg.__file__).parent
        
        # Find all plugin subdirectories
        for item in plugins_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_'):
                try:
                    # Import the plugin module
                    module = import_module(f"kimi_vault.plugins.{item.name}.plugin")
                    
                    # Find the Plugin subclass
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, Plugin) and 
                            attr is not Plugin):
                            self.register_plugin(attr)
                            break
                            
                except ImportError as e:
                    print(f"Warning: Could not load plugin '{item.name}': {e}", file=sys.stderr)
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name"""
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[str]:
        """List names of loaded plugins"""
        return list(self._plugins.keys())
    
    def list_commands(self) -> List[str]:
        """List all available commands in 'plugin.command' format"""
        return list(self._commands.keys())
    
    def execute_command(self, full_command: str, args: List[str]) -> Any:
        """
        Execute a plugin command.
        
        Args:
            full_command: Command in format 'plugin.command' (e.g., 'gmail.unread')
            args: Command-line arguments
        
        Returns:
            Command result
        """
        if full_command not in self._commands:
            raise PluginError(f"Unknown command: {full_command}")
        
        plugin_name, cmd = self._commands[full_command]
        
        # Parse args
        parsed_args = {}
        for i, (arg_name, _, required) in enumerate(cmd.args):
            if i < len(args):
                parsed_args[arg_name] = args[i]
            elif required:
                raise PluginError(f"Missing required argument: {arg_name}")
        
        return cmd.handler(**parsed_args)
    
    def get_command_help(self, full_command: Optional[str] = None) -> str:
        """
        Get help text for commands.
        
        Args:
            full_command: Specific command (e.g., 'gmail.unread') or None for all
        """
        if full_command:
            if full_command not in self._commands:
                return f"Unknown command: {full_command}"
            
            _, cmd = self._commands[full_command]
            lines = [f"{full_command} - {cmd.description}"]
            for arg_name, arg_help, required in cmd.args:
                req_marker = " (required)" if required else ""
                lines.append(f"  {arg_name}: {arg_help}{req_marker}")
            return "\n".join(lines)
        
        # Show all commands
        lines = ["Available commands:"]
        for full_name, (plugin_name, cmd) in sorted(self._commands.items()):
            lines.append(f"  {full_name:30} - {cmd.description}")
        return "\n".join(lines)
