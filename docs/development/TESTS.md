---
title: Testing Guide
nav_order: 50
---

# Testing Guide

Complete guide to testing kimi-secrets-vault, including architecture, patterns, and lessons learned.

---

## Test Suite Status

**Current Status**: ✅ **All 77 tests passing**

| Category | Count | Location |
|----------|-------|----------|
| Unit tests | 21 | `tests/unit/` |
| Integration tests | 56 | `tests/integration/` |
| **Total** | **77** | `tests/` |

**Coverage Goals**:
- Unit tests: 90%+ coverage of core components (vault, plugin base)
- Integration tests: Critical paths for CLI and plugin interactions
- External dependencies: Always mocked (never test real encryption or APIs)

---

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── unit/                    # Isolated component tests
│   ├── test_vault.py        # Vault core functionality
│   └── test_plugin.py       # Plugin base classes
└── integration/             # Component interaction tests
    ├── test_cli.py          # CLI command parsing and execution
    └── test_gmail_plugin.py # Gmail plugin-specific tests
```

### Unit vs Integration Tests

| Type | Purpose | Isolation |
|------|---------|-----------|
| **Unit** | Test individual components in isolation | All dependencies mocked |
| **Integration** | Test component interactions | External services mocked, internal components real |

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src/kimi_vault

# Run specific test file
python -m pytest tests/unit/test_vault.py -v

# Run specific test
python -m pytest tests/unit/test_vault.py::test_decrypt_success -v

# Run integration tests only
python -m pytest tests/integration/ -v

# Run unit tests only
python -m pytest tests/unit/ -v
```

---

## Test Architecture & Patterns

### Core Testing Philosophy

1. **Mock External Dependencies**: Never test actual age encryption or external APIs
2. **Isolate File System**: All file operations must be mocked
3. **Test Behavior, Not Implementation**: Verify what code does, not how it does it
4. **Cover Error Paths**: Test both success and failure cases

### Essential Mocking Patterns

#### 1. File Operations

```python
from unittest.mock import mock_open, patch, Mock
from pathlib import Path

# Pattern: Mock open() as context manager
mock_file = mock_open(read_data='{"key": "value"}')
with patch('builtins.open', mock_file):
    with open('/path/to/file') as f:
        data = f.read()

# Pattern: Mock json.load() directly
with patch('json.load', return_value={'key': 'value'}):
    # Code that uses json.load()
    pass

# Pattern: Mock Path objects
mock_path = Mock(spec=Path)
mock_path.exists.return_value = True
mock_path.__truediv__.return_value = mock_path  # For / operator

# Pattern: Mock vault.decrypt() returning Path
mock_vault.decrypt.return_value = mock_path
```

#### 2. Vault Operations

```python
# Critical: vault.decrypt() returns Path, not string!
mock_path = Mock(spec=Path)
mock_path.exists.return_value = True
mock_vault.decrypt.return_value = mock_path

# Mock file system operations
with patch('os.chmod') as mock_chmod:
    with patch('os.remove') as mock_remove:
        # Test file operations
        pass
```

#### 3. CLI Testing

```python
import sys
from unittest.mock import patch

# Pattern: Patch sys.argv for CLI arguments
with patch('sys.argv', ['kimi-vault', 'encrypt', 'input.txt']):
    from kimi_vault.cli.main import main
    main()

# Pattern: Mock command execution
with patch('sys.argv', ['kimi-vault', 'gmail.unread']):
    with patch.object(plugin, 'cmd_unread') as mock_cmd:
        mock_cmd.return_value = "5 unread emails"
        main()
        mock_cmd.assert_called_once()
```

#### 4. Error Handling

```python
from kimi_vault.core.plugin import PluginError

# Pattern: Mock exceptions
mock_plugin_manager.get_plugin.side_effect = PluginError("Plugin not found")

# Pattern: Test error output
# CLI prints "❌" emoji, not "Error" text
assert "❌" in captured_output
```

#### 5. Plugin Testing

```python
# Pattern: Mock external API clients
@patch('kimi_vault.plugins.gmail.plugin.GmailClient')
def test_gmail_unread_command(mock_client_class):
    mock_client = Mock()
    mock_client.list_unread.return_value = [
        {'id': '123', 'subject': 'Test Email'}
    ]
    mock_client_class.return_value = mock_client
    
    plugin = GmailPlugin({'credentials': {...}})
    result = plugin.cmd_unread("5")
    
    mock_client.list_unread.assert_called_once_with(5)
    assert "Test Email" in result
```

### Shared Fixtures (conftest.py)

```python
# fixtures available to all tests

def mock_gmail_client():
    """Mock Gmail API client with all required methods"""
    client = Mock()
    client.list_unread.return_value = []
    client.list_inbox.return_value = []
    client.search.return_value = []
    return client

def mock_vault():
    """Mock vault with core methods"""
    vault = Mock()
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    vault.decrypt.return_value = mock_path
    vault.encrypt.return_value = None
    vault.cleanup.return_value = None
    return vault
```

---

## Writing Tests for Plugins

### Unit Test Structure

```python
# tests/test_weather_plugin.py
import pytest
from unittest.mock import Mock, patch
from kimi_vault.plugins.weather.plugin import WeatherPlugin
from kimi_vault.core.plugin import PluginError

def test_weather_plugin_validation():
    """Test credential validation"""
    # Missing credentials should raise PluginError
    with pytest.raises(PluginError):
        plugin = WeatherPlugin({})
        plugin._validate_secrets()

def test_weather_plugin_valid_credentials():
    """Test plugin with valid credentials"""
    plugin = WeatherPlugin({
        'api_key': 'test-key',
        'base_url': 'https://api.example.com'
    })
    plugin._validate_secrets()  # Should not raise

def test_weather_commands():
    """Test command registration"""
    plugin = WeatherPlugin({
        'api_key': 'test-key',
        'base_url': 'https://api.example.com'
    })
    
    commands = plugin.get_commands()
    assert len(commands) > 0
    assert any(cmd.name == 'current' for cmd in commands)
```

### Integration Test Structure

```python
# tests/integration/test_weather_plugin.py
from unittest.mock import Mock, patch, mock_open
from pathlib import Path

def test_weather_cli_integration():
    """Test plugin through CLI"""
    with patch('sys.argv', ['kimi-vault', 'weather.current', 'New York']):
        with patch('kimi_vault.core.vault.Vault.decrypt') as mock_decrypt:
            # Mock vault returning Path object
            mock_path = Mock(spec=Path)
            mock_path.exists.return_value = True
            mock_decrypt.return_value = mock_path
            
            # Mock file operations
            with patch('builtins.open', mock_open(read_data='{}')):
                with patch('json.load', return_value={
                    'weather': {'api_key': 'test'}
                }):
                    # Run CLI
                    from kimi_vault.cli.main import main
                    main()
```

### Testing Best Practices

1. **Isolate Tests**: Each test should mock all external dependencies
2. **Test Error Paths**: Test both success and failure cases
3. **Use Realistic Data**: Mock returns should match actual API response formats
4. **Check Assertions**: Verify mocks were called with correct arguments
5. **Clean Up**: No leftover files or side effects between tests
6. **Mock Path Objects**: Always use `Mock(spec=Path)` not strings
7. **Mock Context Managers**: `open()` needs `__enter__` and `__exit__`

---

## Common Pitfalls & Solutions

| Pitfall | Why It Happens | Solution |
|---------|----------------|----------|
| `vault.decrypt()` returns string | Wrong mock setup | Mock returns `Mock(spec=Path)` |
| `open()` not working as context manager | Missing `__enter__`/`__exit__` | Use `mock_open()` helper |
| `json.load()` fails | Expects file object | Mock `json.load()` directly |
| CLI error shows "❌" not "Error" | Emoji prefix | Check for emoji in assertions |
| File operations fail | Real FS calls | Mock `os.chmod()`, `Path.exists()` |
| Plugin method mismatch | Wrong method name | Check source for actual names |
| Test expects wrong output | Didn't verify actual behavior | Check real output before writing test |

### Specific Examples

**Path vs String:**
```python
# ❌ Wrong
mock_vault.decrypt.return_value = "/tmp/secrets.json"

# ✅ Correct
mock_path = Mock(spec=Path)
mock_vault.decrypt.return_value = mock_path
```

**File Context Manager:**
```python
# ❌ Wrong
with patch('builtins.open') as mock_open:
    data = open('/file').read()

# ✅ Correct
with patch('builtins.open', mock_open(read_data='data')):
    with open('/file') as f:
        data = f.read()
```

**Error Messages:**
```python
# ❌ Wrong
assert "Error" in output

# ✅ Correct
assert "❌" in output
```

---

## Lessons Learned

From fixing 26 failing tests to 77 passing tests, these lessons emerged:

### 1. Read the Source Code First

Always check actual function signatures and return types before writing test assertions. The `vault.decrypt()` method returns a `Path` object, not a string, which caused multiple test failures.

### 2. Mock Exactly What the Code Expects

- `open()` must be mocked as a context manager with `__enter__` and `__exit__` methods
- `json.load()` reads from a file object, so mock it directly
- `Path` objects need `__truediv__` method for division operations

### 3. Understand Error Handling Patterns

- CLI uses "❌" emoji prefix for errors, not "Error" text
- Plugin errors use `PluginError` exception class, not generic `Exception`
- Error output goes to `stdout`, not `stderr`

### 4. Test Expectations Must Match Reality

Don't write tests based on wishful thinking. Check what the code actually returns:
- Gmail plugin returns "1 unread email(s):" not "5 unread email"
- CLI prints specific emoji and formatting

### 5. Mock File System Operations Completely

When testing file operations:
- Mock `os.chmod()` to avoid `FileNotFoundError`
- Mock `Path.exists()` for file existence checks
- Mock `subprocess.run()` for external commands like `shred`

### 6. Use Consistent Mocking Patterns

Follow established patterns from the test suite:
- Use `@patch` decorators for comprehensive mocking
- Mock external APIs completely
- Use shared fixtures for common test data

### 7. Verify All Test Assertions

After fixing tests, run the full test suite to ensure:
- All tests pass (77/77 in this case)
- No new failures introduced
- Coverage remains adequate

---

## Git Hooks for Quality Assurance

To maintain code quality and prevent regressions, git hooks enforce test passing:

### Pre-commit Hook

- **Location**: `.git/hooks/pre-commit`
- **Purpose**: Runs quick tests on staged Python files
- **Behavior**: Tests staged test files, skips if no Python files staged
- **Skip**: `git commit --no-verify`

### Pre-push Hook

- **Location**: `.git/hooks/pre-push`
- **Purpose**: Runs full test suite before allowing push
- **Behavior**: Blocks push if any tests fail
- **Skip**: `git push --no-verify`

### Installation

```bash
# Hooks are installed automatically by install.sh
cd ~/code/kimi-secrets-vault
./install.sh --dev

# Or manually copy from templates
cp git-hooks/pre-commit .git/hooks/
cp git-hooks/pre-push .git/hooks/
chmod +x .git/hooks/pre-commit .git/hooks/pre-push
```

### Benefits

1. **Prevents broken code from leaving workstation** - Final validation before remote
2. **Early detection** - Catches test failures as soon as changes are staged
3. **Automatic quality gate** - No manual steps required
4. **Clear feedback** - Detailed error messages and fix suggestions

---

## Manual Testing

For development and debugging:

```bash
# 1. Install in dev mode
cd ~/code/kimi-secrets-vault
./install.sh --dev

# 2. Add test credentials
vim ~/.kimi-vault/secrets.json

# 3. Encrypt
age -r $(cat ~/.kimi-vault/key.txt.pub) -o ~/.kimi-vault/secrets.json.age ~/.kimi-vault/secrets.json
shred -u ~/.kimi-vault/secrets.json

# 4. Test commands
kimi-vault plugins list           # Should show plugins
kimi-vault <plugin>.<command>     # Test specific command
```

---

## Debugging Failed Tests

```bash
# Run with verbose output
python -m pytest tests/test_file.py -v -s

# Run with pdb on failure
python -m pytest tests/test_file.py --pdb

# Show local variables on failure
python -m pytest tests/test_file.py -v --tb=long

# Run single test with maximum detail
python -m pytest tests/test_file.py::test_name -vvs
```

---

## Adding New Tests

When adding features, follow this checklist:

- [ ] Add unit tests for new core functionality
- [ ] Add integration tests for CLI commands
- [ ] Mock all external dependencies
- [ ] Test error cases and edge cases
- [ ] Verify tests pass: `python -m pytest tests/ -v`
- [ ] Check coverage: `python -m pytest tests/ --cov=src/kimi_vault`
- [ ] Run git hooks: `.git/hooks/pre-push`

---

**Last updated**: 2026-02-01

**See Also**:
- [Plugin Development](./PLUGIN_DEVELOPMENT.md) - Creating plugins with tests
- [Architecture](./ARCHITECTURE.md) - System design and security model
- [README](./README.md) - Project overview