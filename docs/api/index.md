---
title: API Reference
nav_order: 90
---

# API Reference

## Overview

Nakimi provides both a CLI and a Python API for programmatic access. This document covers the Python API for plugin development and integration.

## Core Modules

### `nakimi.core`

The core module provides vault management and configuration.

```python
from nakimi.core import Vault, get_config, secure_delete
```

#### `Vault` Class

Main vault interface for encryption/decryption operations.

```python
class Vault:
    def __init__(self, config=None):
        """Initialize vault with optional config."""
    
    def decrypt(self, encrypted_path: str) -> str:
        """Decrypt file and return path to temporary plaintext.
        
        Args:
            encrypted_path: Path to .age encrypted file
        
        Returns:
            Path to temporary plaintext file (in RAM disk)
        
        Raises:
            DecryptionError: If decryption fails
        """
    
    def encrypt(self, plaintext_path: str, output_path: str = None) -> str:
        """Encrypt file with vault's public key.
        
        Args:
            plaintext_path: Path to plaintext file
            output_path: Optional output path (defaults to plaintext_path + '.age')
        
        Returns:
            Path to encrypted file
        """
    
    def init(self, force: bool = False) -> tuple[str, str]:
        """Generate new age key pair.
        
        Args:
            force: Overwrite existing keys
        
        Returns:
            Tuple of (private_key_path, public_key_path)
        """
```

#### `get_config()` Function

```python
def get_config() -> Config:
    """Get current configuration.
    
    Reads from (in order):
    1. Environment variables
    2. Config file (~/.config/nakimi/config)
    3. Default values
    
    Returns:
        Config object with attributes:
        - vault_dir: Path to vault directory
        - key_file: Path to private key
        - secrets_file: Path to encrypted secrets
    """
```

#### `secure_delete()` Function

```python
def secure_delete(path: str) -> None:
    """Securely delete a file using shred.
    
    Args:
        path: File to delete
    
    Note:
        Falls back to regular deletion if shred unavailable
    """
```

### `nakimi.core.plugin`

Plugin base classes and utilities.

```python
from nakimi.core.plugin import Plugin, PluginCommand, PluginError
```

#### `Plugin` Abstract Base Class

Base class for all plugins.

```python
class Plugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name (must match secrets.json key)."""
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Short description shown in plugin list."""
    
    @abstractmethod
    def get_commands(self) -> list[PluginCommand]:
        """Return list of commands this plugin provides."""
    
    def _validate_secrets(self) -> None:
        """Validate plugin-specific secrets.
        
        Override to check required fields in self.secrets.
        Raises PluginError if validation fails.
        """
    
    # Available attributes:
    # self.secrets: Dict[str, Any] - Plugin's secrets from vault
    # self.config: Config - Global configuration
```

#### `PluginCommand` Class

```python
@dataclass
class PluginCommand:
    name: str
    description: str
    handler: Callable
    args: list[str]  # Argument names for help display
```

#### `PluginError` Exception

```python
class PluginError(Exception):
    """Base exception for plugin errors."""
```

## Plugin Development Example

### Complete Plugin Implementation

```python
# src/nakimi/plugins/example/plugin.py
from nakimi.core.plugin import Plugin, PluginCommand, PluginError

class ExamplePlugin(Plugin):
    @property
    def name(self) -> str:
        return "example"
    
    @property
    def description(self) -> str:
        return "Example plugin demonstrating the API"
    
    def _validate_secrets(self):
        # Check required fields
        required = ['api_key', 'endpoint']
        missing = [f for f in required if f not in self.secrets]
        if missing:
            raise PluginError(f"Missing required fields: {missing}")
    
    def get_commands(self) -> list[PluginCommand]:
        return [
            PluginCommand(
                name="status",
                description="Check service status",
                handler=self.cmd_status,
                args=[]
            ),
            PluginCommand(
                name="fetch",
                description="Fetch data by ID",
                handler=self.cmd_fetch,
                args=["id"]
            ),
        ]
    
    def cmd_status(self) -> str:
        """Command handler example."""
        import requests
        try:
            response = requests.get(
                self.secrets['endpoint'] + '/status',
                headers={'Authorization': f"Bearer {self.secrets['api_key']}"}
            )
            response.raise_for_status()
            return f"Service status: {response.json()['status']}"
        except Exception as e:
            return f"Error: {e}"
    
    def cmd_fetch(self, item_id: str) -> str:
        """Command handler with arguments."""
        # Arguments come as strings from CLI
        return f"Would fetch item {item_id}"
```

### Plugin Registration

Plugins are auto-discovered via Python's entry point system. No manual registration needed.

**Requirements**:
1. Plugin class must be in `plugin.py` file
2. Located in `src/nakimi/plugins/<plugin_name>/`
3. Class name must be `<PluginName>Plugin` (e.g., `ExamplePlugin`)

## Using Plugins Programmatically

### Direct Plugin Instantiation

```python
from nakimi.core import Vault, get_config
from nakimi.plugins.gmail.plugin import GmailPlugin

# Load secrets
config = get_config()
vault = Vault()
temp_path = vault.decrypt(config.secrets_file)

import json
with open(temp_path) as f:
    secrets = json.load(f)

# Instantiate plugin
plugin = GmailPlugin()
plugin.secrets = secrets['gmail']
plugin.config = config

# Use plugin commands
commands = plugin.get_commands()
status_cmd = next(c for c in commands if c.name == 'profile')
result = status_cmd.handler()  # Calls cmd_profile()
print(result)

# Clean up
secure_delete(temp_path)
```

### Plugin Manager

For advanced use cases, use the plugin manager directly:

```python
from nakimi.core.plugin_manager import PluginManager

manager = PluginManager()
manager.load_plugins(secrets)  # secrets dict from vault

# Get specific plugin
gmail_plugin = manager.get_plugin('gmail')

# Execute command
result = manager.execute_command('gmail', 'unread', ['5'])
print(result)
```

## CLI Integration

### Adding New CLI Commands

Plugins automatically get CLI commands via the pattern:

```
nakimi <plugin_name>.<command_name> [args]
```

Example: `nakimi example.fetch 123`

### Custom Argument Parsing

For complex arguments, use `argparse` style in your command handler:

```python
def cmd_search(self, query: str, limit: str = "10") -> str:
    # limit comes as string from CLI
    limit_int = int(limit)
    # ... implementation
```

## Session Management

### Programmatic Sessions

```python
from nakimi.core.session import Session

with Session() as session:
    # session.decrypted_path available
    secrets = session.load_secrets()
    # Use secrets...
    gmail_secrets = secrets['gmail']
    # Session automatically cleans up on exit
```

## Error Handling

### Common Exceptions

```python
from nakimi.core.exceptions import (
    DecryptionError,      # Age decryption failed
    EncryptionError,      # Age encryption failed
    ConfigError,          # Configuration problem
    PluginLoadError,      # Plugin failed to load
    CommandError,         # Command execution failed
)

try:
    vault.decrypt('secrets.json.age')
except DecryptionError as e:
    print(f"Decryption failed: {e}")
```

### Plugin Error Reporting

Plugins should raise `PluginError` for user-facing errors:

```python
def cmd_send_email(self, to: str, subject: str, body: str) -> str:
    if not to or '@' not in to:
        raise PluginError("Invalid email address")
    # ... implementation
```

## Configuration API

### Environment Variables

```python
import os
os.environ['NAKIMI_DIR'] = '/custom/path'
os.environ['NAKIMI_KEY'] = '/custom/key.txt'

# Reload config
from nakimi.core import reload_config
config = reload_config()
```

### Config File

```python
from nakimi.core.config import write_config

write_config({
    'vault_dir': '~/.nakimi',
    'key_file': '~/.nakimi/key.txt',
    'secrets_file': '~/.nakimi/secrets.json.age',
})
```

## Testing Utilities

### Plugin Testing

```python
from nakimi.core.plugin import Plugin
from nakimi.core.config import Config

class TestPlugin(Plugin):
    # ... implementation

def test_plugin():
    plugin = TestPlugin()
    plugin.secrets = {'api_key': 'test'}
    plugin.config = Config()
    
    # Test validation
    plugin._validate_secrets()  # Should not raise
    
    # Test commands
    commands = plugin.get_commands()
    assert len(commands) > 0
    
    # Test command execution
    result = commands[0].handler()
    assert isinstance(result, str)
```

### Mock Vault for Tests

```python
from unittest.mock import patch, Mock
from nakimi.core import Vault

def test_with_mock_vault():
    mock_vault = Mock(spec=Vault)
    mock_vault.decrypt.return_value = '/tmp/test.json'
    
    with patch('nakimi.core.Vault', return_value=mock_vault):
        # Test code that uses vault
        pass
```

## Performance Considerations

### Lazy Loading

Plugins are lazy-loaded - they only initialize when first accessed.

### Secret Caching

Secrets are cached per session. Repeated decryption within a session uses cached plaintext.

### Memory Usage

Large secrets may impact memory usage. Consider:
- Splitting secrets into multiple plugin sections
- Using references to external encrypted files
- Cleaning up unused plugin instances

## Best Practices

### API Usage

1. **Always clean up**: Use context managers or explicit `secure_delete()`
2. **Validate inputs**: Check arguments before processing
3. **Handle errors gracefully**: Provide helpful error messages
4. **Log appropriately**: Use Python's logging module for debugging
5. **Test thoroughly**: Write unit tests for your plugin code

### Security

1. **Never log secrets**: Avoid printing secrets to console or logs
2. **Minimize exposure**: Keep plaintext in memory for shortest time possible
3. **Validate TLS**: Ensure API calls use proper certificate validation
4. **Sanitize inputs**: Prevent injection attacks in command handlers

## Examples

See the existing plugins for real-world examples:

- `src/nakimi/plugins/gmail/` - Gmail API integration
- `src/nakimi/plugins/calendar/` - Google Calendar integration (planned)

## Further Reading

- [Plugin Development Guide](../development/PLUGIN_DEVELOPMENT.md)
- [Architecture](../development/ARCHITECTURE.md)
- [Testing Guide](../development/TESTS.md)

---

*Last updated: 2026-02-01*