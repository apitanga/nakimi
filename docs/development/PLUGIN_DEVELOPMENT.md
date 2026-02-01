---
title: Plugin Development Guide
nav_order: 30
---

# Plugin Development Guide

Creating plugins for kimi-secrets-vault is straightforward. This guide walks through the process.

---

## Plugin Anatomy

Every plugin needs:

1. **Directory**: `src/kimi_vault/plugins/<name>/`
2. **`__init__.py`**: Makes it a Python package
3. **`plugin.py`**: Implements the `Plugin` base class
4. **(Optional)** **client.py**: Service-specific API client

---

## Minimal Plugin Example

### 1. Create Directory Structure

```bash
mkdir -p src/kimi_vault/plugins/weather
touch src/kimi_vault/plugins/weather/__init__.py
```

### 2. Implement Plugin Class

**File**: `src/kimi_vault/plugins/weather/plugin.py`

```python
from kimi_vault.core.plugin import Plugin, PluginCommand, PluginError

class WeatherPlugin(Plugin):
    """Weather API integration"""

    @property
    def name(self) -> str:
        """Plugin name (used in CLI)"""
        return "weather"

    @property
    def description(self) -> str:
        """Human-readable description"""
        return "Weather API integration"

    def _validate_secrets(self):
        """Validate required credentials exist"""
        required = ['api_key', 'base_url']
        missing = [f for f in required if not self.secrets.get(f)]
        if missing:
            raise PluginError(f"Missing credentials: {', '.join(missing)}")

    def get_commands(self) -> list[PluginCommand]:
        """Register available commands"""
        return [
            PluginCommand(
                name="current",
                description="Get current weather for a city",
                handler=self.cmd_current,
                args=["city"]
            ),
        ]

    def cmd_current(self, city: str) -> str:
        """Get current weather"""
        import requests

        api_key = self.secrets['api_key']
        base_url = self.secrets['base_url']

        response = requests.get(
            f"{base_url}/weather",
            params={"q": city, "appid": api_key}
        )
        response.raise_for_status()

        data = response.json()
        return f"Weather in {city}: {data['weather'][0]['description']}, {data['main']['temp']}°K"
```

### 3. Add Credentials Template

Update `config/secrets.template.json`:

```json
{
  "gmail": { ... },
  "weather": {
    "api_key": "your-openweathermap-api-key",
    "base_url": "https://api.openweathermap.org/data/2.5"
  }
}
```

### 4. Use Your Plugin

```bash
# Add credentials to vault
vim ~/.kimi-vault/secrets.json  # Add weather credentials
age -r $(cat ~/.kimi-vault/key.txt.pub) -o ~/.kimi-vault/secrets.json.age ~/.kimi-vault/secrets.json
shred -u ~/.kimi-vault/secrets.json

# Use the plugin
kimi-vault weather.current "New York"
```

---

## Plugin Base Class API

### Required Methods

```python
@property
def name(self) -> str:
    """Plugin identifier (lowercase, no spaces)"""

@property
def description(self) -> str:
    """Human-readable description"""

def _validate_secrets(self):
    """Validate credentials (raise PluginError if invalid)"""

def get_commands(self) -> list[PluginCommand]:
    """Return list of available commands"""
```

### Available Properties

```python
self.secrets: dict         # Decrypted credentials for this plugin
self.name: str            # Plugin name
self.description: str     # Plugin description
```

### Command Handler Signature

```python
def cmd_<name>(self, *args) -> str:
    """
    Command handler.

    Args:
        *args: Positional arguments from CLI

    Returns:
        str: Output to display to user

    Raises:
        PluginError: On validation or execution errors
    """
```

---

## Plugin Discovery

Plugins are auto-discovered based on:

1. **Location**: Must be in `src/kimi_vault/plugins/<name>/`
2. **Credentials**: Must have matching key in `secrets.json`
3. **Import**: Must be importable as `kimi_vault.plugins.<name>.plugin.<Name>Plugin`

**Example**:
- Plugin location: `src/kimi_vault/plugins/github/`
- Class: `GithubPlugin` in `src/kimi_vault/plugins/github/plugin.py`
- Credentials: `secrets.json` contains `"github": { ... }`

**Result**: Plugin auto-loads when `kimi-vault` CLI starts.

---

## Advanced: Separate Client Class

For complex APIs, separate the API client from the plugin.

### Example: Gmail Plugin Structure

**File**: `src/kimi_vault/plugins/gmail/client.py`

```python
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GmailClient:
    """Gmail API client (handles OAuth, API calls)"""

    def __init__(self, secrets: dict):
        self.secrets = secrets
        self._service = None

    def _get_service(self):
        """Lazy-load Gmail API service"""
        if self._service is None:
            creds = Credentials.from_authorized_user_info(
                self.secrets['credentials']
            )

            # Refresh if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

            self._service = build('gmail', 'v1', credentials=creds)

        return self._service

    def list_unread(self, max_results: int = 10):
        """List unread emails"""
        service = self._get_service()
        results = service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        # ... process and return
```

**File**: `src/kimi_vault/plugins/gmail/plugin.py`

```python
from kimi_vault.core.plugin import Plugin, PluginCommand
from .client import GmailClient

class GmailPlugin(Plugin):
    """Gmail integration"""

    def __init__(self, secrets: dict):
        super().__init__(secrets)
        self.client = GmailClient(secrets)

    @property
    def name(self) -> str:
        return "gmail"

    def get_commands(self) -> list[PluginCommand]:
        return [
            PluginCommand(
                name="unread",
                description="List unread emails",
                handler=self.cmd_unread,
                args=["limit?"]
            ),
        ]

    def cmd_unread(self, limit: str = "10") -> str:
        """List unread emails"""
        emails = self.client.list_unread(int(limit))
        # Format and return output
```

**Benefits**:
- Clean separation of concerns
- Testable API client
- Plugin focuses on CLI interface
- Client can be reused outside plugin context

---

## Error Handling

### PluginError

Use `PluginError` for validation and execution errors:

```python
from kimi_vault.core.plugin import PluginError

def cmd_send(self, to: str, subject: str, body: str) -> str:
    if not to:
        raise PluginError("Recipient email is required")

    if '@' not in to:
        raise PluginError(f"Invalid email address: {to}")

    # ... send email
```

### HTTP Errors

Let HTTP exceptions bubble up (or catch and convert to PluginError):

```python
import requests

def cmd_fetch(self, url: str) -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.HTTPError as e:
        raise PluginError(f"HTTP error: {e}")
```

---

## Testing Plugins

See [TESTS.md](./TESTS.md) for comprehensive testing documentation including:
- Unit and integration test patterns
- Mocking file operations and external APIs
- CLI integration testing
- Common pitfalls and solutions
- Test fixtures and best practices

Quick reference for plugin testing:

```python
# tests/test_weather_plugin.py
import pytest
from unittest.mock import Mock, patch
from kimi_vault.plugins.weather.plugin import WeatherPlugin
from kimi_vault.core.plugin import PluginError

def test_weather_plugin_validation():
    """Test credential validation"""
    with pytest.raises(PluginError):
        plugin = WeatherPlugin({})
        plugin._validate_secrets()

def test_weather_commands():
    """Test command registration"""
    plugin = WeatherPlugin({'api_key': 'test', 'base_url': 'http://api'})
    commands = plugin.get_commands()
    assert any(cmd.name == 'current' for cmd in commands)
```

---

## Best Practices

### 1. Lazy Loading

Don't initialize expensive resources in `__init__`:

```python
class MyPlugin(Plugin):
    def __init__(self, secrets: dict):
        super().__init__(secrets)
        self._client = None  # Don't initialize here

    def _get_client(self):
        """Lazy-load API client"""
        if self._client is None:
            self._client = ExpensiveClient(self.secrets)
        return self._client
```

### 2. Token Refresh

Handle expired tokens gracefully:

```python
def _refresh_token_if_needed(self, creds):
    """Auto-refresh expired tokens"""
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        # Update secrets with new token
        self.secrets['credentials']['token'] = creds.token
    return creds
```

### 3. Retry Logic

Add retries for transient failures:

```python
import time

def _api_call_with_retry(self, fn, max_retries=3):
    """Retry API calls on transient failures"""
    for attempt in range(max_retries):
        try:
            return fn()
        except requests.ConnectionError as e:
            if attempt == max_retries - 1:
                raise PluginError(f"API call failed after {max_retries} retries: {e}")
            time.sleep(2 ** attempt)  # Exponential backoff
```

### 4. Clear Error Messages

```python
# Bad
raise PluginError("Error")

# Good
raise PluginError(f"Failed to fetch weather for '{city}': API returned 404 Not Found")
```

### 5. Validate Input

```python
def cmd_send(self, to: str, subject: str, body: str) -> str:
    # Validate email
    if '@' not in to:
        raise PluginError(f"Invalid email: {to}")

    # Validate length
    if len(subject) > 200:
        raise PluginError(f"Subject too long ({len(subject)} chars, max 200)")

    # ... proceed with sending
```

---

## Plugin Ideas

Here are some plugin ideas to get you started:

| Plugin | Description | Credentials Needed |
|--------|-------------|-------------------|
| **calendar** | Google Calendar integration | OAuth2 credentials |
| **github** | GitHub API (issues, PRs, repos) | Personal access token |
| **slack** | Slack messaging | Slack app token |
| **jira** | Jira issue management | API token |
| **aws** | AWS service calls | Access key + secret |
| **notion** | Notion API | Integration token |
| **todoist** | Task management | API token |
| **spotify** | Music control | OAuth2 credentials |

---

## Publishing Your Plugin

If you create a useful plugin, consider contributing it back:

1. Fork https://github.com/apitanga/kimi-secrets-vault
2. Create plugin in `src/kimi_vault/plugins/<name>/`
3. Add documentation in `docs/<NAME>_SETUP.md`
4. Update `config/secrets.template.json`
5. Add tests in `tests/test_<name>_plugin.py`
6. Submit PR with:
   - Plugin code
   - Setup documentation
   - Credentials template
   - Tests


**Last updated**: 2026-02-01