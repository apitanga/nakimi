---
title: Architecture Decision Records
nav_order: 34
parent: Development
---

# Architecture Decision Records

Key design decisions and their rationale for nakimi.

---

### ADR-001: Why age over GPG?

**Status**: Accepted

**Context**:
- Need encrypted storage for API credentials
- GPG is complex, hard to use correctly
- age is modern, simple, auditable

**Decision**: Use [age](https://age-encryption.org) for encryption

**Consequences**:
- ✅ Simple key management (one file)
- ✅ Fast encryption/decryption
- ✅ No trust web complexity
- ❌ Requires `age` CLI tool (external dependency)

**Alternatives Considered**:
- **GPG**: Too complex, poor UX
- **Python cryptography library**: Would need to manage keys ourselves
- **AWS KMS**: Vendor lock-in, requires AWS account

---

### ADR-002: Plugin Auto-Discovery

**Status**: Accepted

**Context**:
- Don't want to manually register plugins
- Plugin availability should depend on credentials
- DRY principle: credentials define what's available

**Decision**: Auto-discover plugins based on `secrets.json` keys

**Implementation**:
```python
# Plugin loads if secrets.json contains matching key
{
  "gmail": { ... },      # GmailPlugin loads
  "calendar": { ... }    # CalendarPlugin loads
}
```

**Consequences**:
- ✅ No manual plugin registration
- ✅ Adding credentials = plugin auto-loads
- ✅ Missing credentials = plugin doesn't load
- ❌ Plugin name must match secrets key (convention)

**Alternatives Considered**:
- **Manual registration**: Too much boilerplate
- **Config file**: Extra file to maintain

---

### ADR-003: Just-in-Time Decryption

**Status**: Accepted

**Context**:
- Don't want secrets in memory longer than needed
- Decrypting at startup = secrets exposed for entire session
- Decrypting per-command = too slow

**Decision**: Decrypt secrets to temp file at session start, shred at session end

**Implementation**:
```python
# Session mode
vault.decrypt()  # Decrypt to temp file
# ... use plugins (read from temp file)
vault.cleanup()  # Shred temp file

# Command mode
with vault.session():
    plugin.execute()  # Auto-decrypt + auto-cleanup
```

**Consequences**:
- ✅ Secrets only exposed during session
- ✅ Fast plugin access (no per-command decryption)
- ✅ Auto-cleanup on exit
- ❌ Temp file exists during session (mitigated by strict permissions)

**Alternatives Considered**:
- **Decrypt per-command**: Too slow
- **Keep in memory**: Higher attack surface
- **Decrypt at startup**: Secrets exposed for entire process lifetime

---

### ADR-004: CLI Command Syntax

**Status**: Accepted

**Context**:
- Need intuitive CLI syntax
- Multiple plugins with multiple commands
- Don't want nested subcommands

**Decision**: Use `plugin.command` syntax

**Examples**:
```bash
nakimi gmail.unread
nakimi gmail.search "query"
nakimi calendar.today
nakimi github.issues
```

**Consequences**:
- ✅ Clear, readable syntax
- ✅ No deep nesting
- ✅ Easy to discover (tab completion friendly)
- ❌ Can't have commands with dots in name (non-issue in practice)

**Alternatives Considered**:
- **Subcommands**: `nakimi gmail unread` (more typing, less clear)
- **Flags**: `nakimi --plugin=gmail --command=unread` (too verbose)
- **Combined**: `nakimi gmail-unread` (loses semantic grouping)

---

### ADR-005: Secure Deletion with shred

**Status**: Accepted (updated 2026-02-03)

**Context**:
- `rm` doesn't actually delete file data from physical storage
- Temp files on disk could be recovered after deletion
- Need to prevent credential leakage
- Temp files on RAM-backed filesystems (tmpfs / `/dev/shm`) never touch physical storage, so overwriting is unnecessary there

**Decision**: Use `shred -u` for files on physical storage. Skip it for files already on tmpfs, where a plain `unlink` is sufficient. Fall back to `unlink` if `shred` is unavailable (e.g. macOS).

**Implementation**:
```python
def secure_delete(file_path):
    path = Path(file_path)
    if not path.exists():
        return

    # On tmpfs: data was never on disk, plain delete is fine
    if is_ram_disk(path):
        path.unlink()
        return

    # On physical storage: overwrite then delete (best effort on SSDs)
    try:
        subprocess.run(["shred", "-u", str(path)], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        path.unlink()  # fallback if shred unavailable
```

**Consequences**:
- ✅ Prevents file recovery when secrets land on physical storage
- ✅ No unnecessary overwrite passes for files already in RAM (tmpfs)
- ✅ Graceful fallback — works on macOS and systems without `shred`
- ⚠️ `shred` is best-effort on SSDs/journaling filesystems (wear leveling can retain old blocks); the primary defense against this is keeping secrets on tmpfs in the first place

**Alternatives Considered**:
- **os.remove() only**: Doesn't overwrite data on physical storage
- **Manual overwrite**: Complex, error-prone, same SSD caveats as shred
- **macOS rm -P**: Works but non-portable; handled here via the fallback path

---

### ADR-006: Plugin Base Class Pattern

**Status**: Accepted

**Context**:
- Need consistent plugin interface
- Want to enforce required methods
- Python doesn't have interfaces

**Decision**: Use abstract base class with required properties/methods

**Implementation**:
```python
from abc import ABC, abstractmethod

class Plugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def get_commands(self) -> list[PluginCommand]:
        pass
```

**Consequences**:
- ✅ Enforces plugin contract
- ✅ Clear interface for plugin developers
- ✅ Runtime validation
- ❌ More boilerplate than duck typing

**Alternatives Considered**:
- **Duck typing**: No enforcement, easy to break
- **Protocol (typing.Protocol)**: Runtime checks require isinstance, not auto-enforced

---

### ADR-007: Separate Client Classes

**Status**: Accepted (for complex APIs)

**Context**:
- Gmail plugin has complex OAuth flow
- API client logic mixed with CLI logic = messy
- Want to reuse client outside plugin context

**Decision**: Separate API client from plugin (for complex integrations)

**Structure**:
```
plugins/gmail/
├── plugin.py      # CLI interface (thin wrapper)
└── client.py      # API client (OAuth, API calls)
```

**When to use**:
- ✅ Complex API (OAuth, pagination, retries)
- ✅ Reusable client (might use outside plugin)
- ❌ Simple API (single HTTP call) - keep in plugin.py

**Consequences**:
- ✅ Clean separation of concerns
- ✅ Reusable API client
- ✅ Plugin focuses on CLI interface
- ❌ Extra file for simple plugins

---

### ADR-008: Environment Variables for Config

**Status**: Accepted

**Context**:
- Need configurable paths (vault dir, key file)
- Config file adds complexity
- Environment variables are standard

**Decision**: Use environment variables with sensible defaults

**Implementation**:
```python
VAULT_DIR = os.getenv('NAKIMI_DIR', os.path.expanduser('~/.nakimi'))
KEY_FILE = os.getenv('NAKIMI_KEY', f'{VAULT_DIR}/key.txt')
```

**Consequences**:
- ✅ No config file needed
- ✅ Easy to override
- ✅ Standard pattern
- ❌ Less discoverable than config file (mitigated by documentation)

---

### ADR-009: Python Package Structure

**Status**: Accepted

**Context**:
- Want installable package
- Need proper distribution
- Eventually publish to PyPI

**Decision**: Use modern Python packaging (pyproject.toml + setuptools)

**Structure**:
```
nakimi/
├── src/nakimi/    # Source code
├── tests/             # Tests
├── pyproject.toml     # Package metadata
└── install.sh         # Convenience installer
```

**Consequences**:
- ✅ Standard Python packaging
- ✅ Ready for PyPI
- ✅ Editable install for development
- ✅ Proper dependency management

**Alternatives Considered**:
- **setup.py**: Deprecated in favor of pyproject.toml
- **Poetry**: Too opinionated, adds complexity

---

### ADR-010: No Database

**Status**: Accepted

**Context**:
- Could use SQLite to store metadata (last refresh, etc.)
- Adds complexity, attack surface
- File-based approach is simpler

**Decision**: No database, use encrypted JSON file

**Consequences**:
- ✅ Simple, auditable
- ✅ Easy to backup (one file)
- ✅ No database dependencies
- ❌ Limited query capabilities (not needed for this use case)