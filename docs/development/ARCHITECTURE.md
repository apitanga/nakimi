---
title: Architecture
nav_order: 32
parent: Development
---

# Architecture

System design and implementation of kimi-secrets-vault.

---

## Core Principles

1. **Security First** - Credentials never stored in plaintext
2. **Simple > Complex** - Avoid over-engineering
3. **Plugin-based** - Easy to extend
4. **Just-in-time** - Decrypt only when needed
5. **Auto-cleanup** - Secure deletion, no leftover temp files

---

## System Architecture

### High-Level Flow

```
User runs CLI command
       ↓
CLI parses plugin.command syntax
       ↓
Plugin Manager discovers loaded plugins
       ↓
Route command to correct plugin
       ↓
Plugin requests secrets from Vault
       ↓
Vault decrypts secrets.json.age → temp file
       ↓
Plugin loads secrets from temp file
       ↓
Plugin executes command
       ↓
Return output to CLI
       ↓
Vault shreds temp file (on session end)
```

### Component Layers

```
┌──────────────────────────────────────────────────────────────┐
│                       CLI Layer                              │
│  • Command parsing (plugin.command)                          │
│  • Argument handling                                         │
│  • Output formatting                                         │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                    Plugin Manager                            │
│  • Auto-discovery of plugins                                 │
│  • Command routing                                           │
│  • Secret injection                                          │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                    Plugin Layer                              │
│  • Service-specific logic                                    │
│  • API clients                                               │
│  • Command handlers                                          │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                      Vault Core                              │
│  • age encryption/decryption                                 │
│  • Temp file management                                      │
│  • Secure deletion (shred)                                   │
└──────────────────────────────────────────────────────────────┘
```

---

## Security Model

### Threat Model

**In Scope**:
- Credentials stolen from disk at rest
- Credentials leaked via temp files
- Unauthorized access to credentials

**Out of Scope**:
- Memory dumps (not protected)
- Root/admin access (game over anyway)
- Physical access to machine
- Keyloggers

### Security Controls

| Threat | Control | Implementation |
|--------|---------|----------------|
| Credentials on disk | Encryption (age) | `secrets.json.age` |
| Key compromise | File permissions | `chmod 600 key.txt` |
| Temp file leakage | Secure deletion | `shred -u` |
| Unauthorized access | No remote access | Local-only tool |
| Session hijacking | Isolated sessions | Unique temp file per session |

---

## Performance Considerations

### Bottlenecks

1. **Age encryption/decryption**: ~50ms (acceptable)
2. **API calls**: Variable (network dependent)
3. **Token refresh**: ~1-2s (Gmail OAuth)

### Optimizations

- **Lazy loading**: Don't load plugins until needed
- **Session mode**: Decrypt once, use multiple times
- **Token caching**: Refresh only when expired

---

## Code Organization

```
src/kimi_vault/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── vault.py          # Encryption/decryption, file management
│   └── plugin.py         # Plugin base classes, manager
├── cli/
│   ├── __init__.py
│   └── main.py           # CLI command parsing, dispatch
└── plugins/
    ├── __init__.py
    ├── gmail/
    │   ├── __init__.py
    │   ├── plugin.py     # Gmail CLI interface
    │   └── client.py     # Gmail API client
    └── weather/          # Example plugin
        ├── __init__.py
        └── plugin.py
```

### Key Components

1. **Vault (`vault.py`)**
   - `Vault` class: Manages encryption/decryption
   - `decrypt()`: Decrypts to temp file, returns Path
   - `cleanup()`: Securely deletes temp file

2. **Plugin Manager (`plugin.py`)**
   - `Plugin` abstract base class
   - `PluginManager`: Discovers and loads plugins
   - `PluginCommand`: Command definition

3. **CLI (`main.py`)**
   - `main()`: Entry point
   - `parse_args()`: Plugin.command syntax
   - `execute_command()`: Route to plugin

---

## Data Flow

### Session Mode

```
User: kimi-vault session
        ↓
Vault.decrypt() → /tmp/secrets-abc123.json
        ↓
Shell starts with KIMI_VAULT_SECRETS=/tmp/secrets-abc123.json
        ↓
User: kimi-vault gmail.unread
        ↓
Plugin reads from /tmp/secrets-abc123.json
        ↓
User: exit
        ↓
Vault.cleanup() → shred /tmp/secrets-abc123.json
```

### Command Mode

```
User: kimi-vault gmail.unread 5
        ↓
Vault.decrypt() → /tmp/secrets-xyz789.json
        ↓
Plugin executes command
        ↓
Output displayed
        ↓
Vault.cleanup() → shred /tmp/secrets-xyz789.json
```

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `KIMI_VAULT_DIR` | `~/.kimi-vault` | Vault directory |
| `KIMI_VAULT_KEY` | `~/.kimi-vault/key.txt` | Private key file |
| `KIMI_VAULT_SECRETS` | (auto) | Temp secrets file path |

### File Structure

```
~/.kimi-vault/
├── key.txt              # Private key (chmod 600)
├── key.txt.pub         # Public key
└── secrets.json.age    # Encrypted credentials
```

---

## Future Architecture Changes

### MCP Server Mode (Planned)

Add Model Context Protocol server to expose plugins to AI assistants:

```
AI Assistant → MCP Client → MCP Server → Plugins → Vault
```

**Benefits**:
- Direct integration with Claude, ChatGPT, etc.
- No CLI wrapper needed
- Standard protocol (MCP)

### Plugin Marketplace (Future)

Allow third-party plugins:

```
~/.kimi-vault/plugins/
├── community/          # Community plugins
│   ├── twitter/
│   └── linkedin/
└── core/              # Built-in plugins
    ├── gmail/
    └── calendar/
```

### Performance Optimizations

1. **Parallel plugin loading**: Load plugins concurrently
2. **Cached credentials**: Store decrypted credentials in memory for short periods (with security considerations)
3. **Batch API calls**: Combine multiple API requests

---

## Related Documentation

- **[ADR.md](./ADR.md)** - Architecture Decision Records (why specific choices were made)
- **[PLUGIN_DEVELOPMENT.md](./PLUGIN_DEVELOPMENT.md)** - Guide to creating new plugins
- **[TESTS.md](./TESTS.md)** - Testing architecture, patterns, and strategies

---

**Last updated**: 2026-02-01