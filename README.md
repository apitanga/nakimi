# 🔐 Kimi Secrets Vault

Give AI assistants secure access to your APIs without exposing plaintext credentials.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What is this?

A secure vault that stores your API credentials encrypted at rest, decrypts them just-in-time for AI assistant sessions, and automatically cleans up when done.

**Current integrations:**
- ✅ Gmail (read, compose, send)

**Future integrations:**
- 🚧 Google Calendar
- 🚧 GitHub API
- 🚧 Custom APIs

## Why?

When using AI assistants (Kimi, Claude, etc.), you might want them to:
- Check your unread emails
- Look up your calendar
- Query your GitHub issues

But you shouldn't paste credentials into chat. This vault lets assistants access APIs **securely** through encrypted storage + temporary decryption.

## How It Works

```
At Rest                    In Session                    Cleanup
─────────────────────────────────────────────────────────────────────
secrets.json.age    →    /tmp/secrets.json    →    securely shredded
(encrypted)              (temporary only)          (session end)
     ↑                           ↓
     └───────────────────────────┘
        AI assistant uses APIs
        via temporary credentials
```

**Security features:**
- 🔐 [age](https://age-encryption.org) encryption - modern, simple, secure
- ⏱️ Just-in-time decryption - secrets exposed only when needed
- 🧹 Automatic cleanup - secrets shredded (not just deleted) on exit
- 🔄 Token refresh - OAuth tokens refreshed before expiry

## Quick Start

### 1. Install

```bash
git clone https://github.com/YOUR_USERNAME/kimi-secrets-vault.git
cd kimi-secrets-vault
./install.sh
```

### 2. Initialize Vault

```bash
# Generate encryption key pair
kimi-vault init

# Output:
# 🔐 Generating new age key pair...
# ✅ Key generated!
#    Private key: ~/.kimi-vault/key.txt
#    Public key: age1...
#
# ⚠️  IMPORTANT: Back up your private key!
```

### 3. Add API Credentials

**For Gmail** (see [docs/GMAIL_SETUP.md](docs/GMAIL_SETUP.md) for detailed instructions):

```bash
# 1. Copy template
cp config/secrets.template.json ~/.kimi-vault/secrets.json

# 2. Edit with your credentials
vim ~/.kimi-vault/secrets.json

# 3. Encrypt
age -r $(cat ~/.kimi-vault/key.txt.pub) \
  -o ~/.kimi-vault/secrets.json.age \
  ~/.kimi-vault/secrets.json

# 4. Securely delete plaintext
shred -u ~/.kimi-vault/secrets.json
```

### 4. Use with AI Assistant

```bash
# Start a secure session
kimi-vault-session

# Inside the session:
$ kimi-vault unread           # List unread emails
$ kimi-vault search "from:boss" # Search emails
```

Or use Python directly:

```python
from kimi_vault import GmailClient

client = GmailClient()
emails = client.list_unread()
for email in emails:
    print(f"{email['subject']} from {email['from']}")
```

## Architecture

The vault is designed to be **extensible**. Each API integration follows this pattern:

```
┌─────────────────────────────────────────────────────────┐
│                    Vault Core                           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │   Config    │  │    Crypto    │  │  Session Mgmt  │ │
│  │  (paths,    │  │  (age enc/   │  │  (env vars,    │ │
│  │   env vars) │  │   dec)       │  │   cleanup)     │ │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘ │
└─────────┼────────────────┼──────────────────┼──────────┘
          │                │                  │
          └────────────────┴──────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │  Gmail   │    │ Calendar │    │  GitHub  │
    │  Client  │    │  (todo)  │    │  (todo)  │
    └──────────┘    └──────────┘    └──────────┘
```

### Adding a New API Integration

To add a new service (e.g., Google Calendar):

1. **Add credentials to secrets template:**
   ```json
   {
     "calendar": {
       "client_id": "...",
       "client_secret": "...",
       "refresh_token": "..."
     }
   }
   ```

2. **Create a client class:**
   ```python
   # src/kimi_vault/calendar_client.py
   from .client import BaseOAuthClient
   
   class CalendarClient(BaseOAuthClient):
       SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
       # ... implement methods
   ```

3. **Add CLI commands:**
   ```python
   # In cli.py
   elif args.command == "calendar":
       events = calendar_client.list_events()
   ```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KIMI_VAULT_DIR` | Vault directory | `~/.kimi-vault` |
| `KIMI_VAULT_KEY` | Private key path | `~/.kimi-vault/key.txt` |
| `KIMI_VAULT_SECRETS` | Encrypted secrets path | `~/.kimi-vault/secrets.json.age` |
| `KIMI_VAULT_CLIENT_ID` | OAuth client ID | (from config) |
| `KIMI_VAULT_CLIENT_SECRET` | OAuth client secret | (from config) |

### Config File

Create `~/.config/kimi-vault/config`:

```bash
# Paths
vault_dir = ~/.kimi-vault
key_file = ~/.kimi-vault/key.txt

# OAuth credentials (optional)
client_id = your-client-id.apps.googleusercontent.com
client_secret = your-client-secret
```

## CLI Reference

### Vault Management

```bash
kimi-vault init              # Initialize vault, generate keys
kimi-vault-session           # Start secure session
kimi-vault-oauth             # Get OAuth refresh tokens
```

### Gmail (Current Integration)

```bash
kimi-vault unread [OPTIONS]
  -n, --limit INTEGER  Maximum emails to show [default: 10]

kimi-vault search QUERY [OPTIONS]
  -n, --limit INTEGER  Maximum emails to show [default: 10]

kimi-vault labels            # List Gmail labels
kimi-vault profile           # Show Gmail profile

kimi-vault draft TO SUBJECT BODY
kimi-vault send TO SUBJECT BODY [--yes]
```

### Calendar (Planned)

```bash
kimi-vault calendar today    # Today's events
kimi-vault calendar week     # This week's events
kimi-vault calendar next     # Next meeting
```

## Python API

### Vault Operations

```python
from kimi_vault import VaultConfig, VaultCrypto

# Configuration (env vars + config file + defaults)
config = VaultConfig()
print(config.vault_dir)      # ~/.kimi-vault
print(config.key_file)       # ~/.kimi-vault/key.txt

# Encryption/decryption
crypto = VaultCrypto()
crypto.encrypt("secrets.json", output_file="secrets.json.age")
decrypted_path = crypto.decrypt("secrets.json.age")

# Secure cleanup
from kimi_vault.crypto import secure_delete
secure_delete(decrypted_path)
```

### Gmail Client

```python
from kimi_vault import GmailClient

# Auto-detects secrets from KIMI_VAULT_SECRETS env var
client = GmailClient()

# Read operations
emails = client.list_unread(max_results=5)
results = client.search_emails("from:boss@example.com")
labels = client.list_labels()
profile = client.get_profile()

# Write operations
draft = client.create_draft(
    to="recipient@example.com",
    subject="Hello",
    body="Message body"
)

sent = client.send_email(
    to="recipient@example.com",
    subject="Hello",
    body="Message body"
)

# Reply to thread
client.reply_to_thread(
    thread_id="123abc",
    to="recipient@example.com",
    subject="Re: Original Subject",
    body="Reply body"
)
```

## Security

- **Encryption**: age (modern, auditable, simple)
- **Key storage**: Private key never leaves your machine
- **At-rest**: All secrets encrypted with your public key
- **In-use**: Decrypted to `/tmp/` with strict permissions (0600)
- **Cleanup**: Securely shredded via `shred` (Linux/Mac) or `rm -P` (BSD)
- **Session isolation**: Each session gets unique temp file

**⚠️ Important:** Back up your `~/.kimi-vault/key.txt` offline (password manager, encrypted USB). Lose this key = lose access to all secrets.

## Requirements

- Python 3.9+
- [age](https://age-encryption.org) encryption tool
- API credentials for services you want to use (Gmail, etc.)

## Installation Methods

### Quick Install
```bash
./install.sh
```

### Development Install
```bash
./install.sh --dev
```

### Manual Install
```bash
pip install -e .
```

## Troubleshooting

See [docs/INSTALL.md](docs/INSTALL.md) and [docs/GMAIL_SETUP.md](docs/GMAIL_SETUP.md) for detailed troubleshooting.

## Roadmap

- [ ] Google Calendar integration
- [ ] GitHub API integration
- [ ] Generic HTTP API client (for custom endpoints)
- [ ] Plugin system for custom integrations
- [ ] Key rotation support
- [ ] Multiple key support (work/personal)

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) (TODO).

## License

MIT License - See [LICENSE](LICENSE) file.
