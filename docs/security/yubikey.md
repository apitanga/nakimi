---
title: YubiKey Integration
nav_order: 85
parent: Security Documentation
---

# YubiKey Integration Guide

## Overview

Nakimi supports optional hardware-based encryption using YubiKey PIV (Personal Identity Verification) slots. This provides an additional security layer by encrypting the age private key with a YubiKey, requiring physical presence and PIN authentication for decryption.

**Key Benefits**:
- **Hardware protection**: Private key encrypted with YubiKey's secure element
- **Multi-factor authentication**: Requires something you have (YubiKey) + something you know (PIN) + optionally something you are (touch)
- **Physical presence**: Decryption requires the YubiKey to be inserted
- **Backward compatibility**: YubiKey is optional; existing installations continue to work

## Requirements

### Hardware Requirements
- YubiKey 4 or 5 series with PIV support
- USB port for YubiKey connection

### Software Requirements
- `yubikey-manager` CLI tool (`ykman`) version 5.0.0 or later
- `age-plugin-yubikey` binary (Rust plugin for age encryption)
- Python package: `yubikey-manager` (optional dependency)

### Installation

#### yubikey-manager

```bash
# Install yubikey-manager
pip install yubikey-manager

# Verify installation
ykman --version
```

#### age-plugin-yubikey

The `age-plugin-yubikey` plugin is required for YubiKey-based age encryption. Install it from the [GitHub releases](https://github.com/str4d/age-plugin-yubikey/releases).

**Linux/macOS**:
```bash
# Using cargo (requires Rust toolchain)
cargo install age-plugin-yubikey

# Or download binary from releases
curl -L https://github.com/str4d/age-plugin-yubikey/releases/latest/download/age-plugin-yubikey-linux-amd64.tgz | tar -xz
sudo mv age-plugin-yubikey /usr/local/bin/
```

**Windows/WSL2**:
Download the Windows binary (`age-plugin-yubikey.exe`) from releases and place it in your PATH. From WSL2, you can run the Windows binary directly.

**Verify installation**:
```bash
age-plugin-yubikey --version
# or for Windows binary
age-plugin-yubikey.exe --version
```

Nakimi will automatically detect and use the plugin when available.

## Configuration

### Environment Variables

Configure YubiKey via environment variables or config file:

```bash
# Enable YubiKey
export NAKIMI_YUBIKEY_ENABLED=true

# Configure PIV slot (default: 1)
export NAKIMI_YUBIKEY_SLOT=1

# Security settings
export NAKIMI_YUBIKEY_REQUIRE_TOUCH=true  # Require touch for operations
export NAKIMI_YUBIKEY_PIN_PROMPT=true     # Prompt for PIN
```

### Configuration File

Add to `~/.config/nakimi/config`:
```ini
yubikey_enabled=true
yubikey_slot=1
yubikey_require_touch=true
yubikey_pin_prompt=true
```

### PIV Slot Selection

Nakimi uses PIV slot `1` by default, which is the standard slot for asymmetric cryptography operations. Supported slots:

- `1` - Default authentication slot
- `9a` - Authentication (alternative)
- `9c` - Digital Signature
- `9d` - Key Management
- `9e` - Card Authentication

**Recommendation**: Use slot `1` (default) unless you have specific requirements.

## Usage

### CLI Commands

Nakimi provides a `yubikey` command group for YubiKey management:

```bash
# Check YubiKey status
nakimi yubikey status

# Initialize YubiKey for Nakimi
nakimi yubikey setup [--slot 1] [--no-touch] [--no-pin-prompt]

# Encrypt existing age key with YubiKey
nakimi yubikey encrypt-key

# Verify PIN
nakimi yubikey verify-pin <PIN>

# Change PIN
nakimi yubikey change-pin <old-pin> <new-pin>

# Test decryption
nakimi yubikey decrypt-key
```

### Step-by-Step Setup

1. **Insert YubiKey** and ensure it's recognized:
   ```bash
   ykman info
   ```

2. **Initialize YubiKey for Nakimi**:
   ```bash
   nakimi yubikey setup
   ```
   This configures the environment but doesn't modify the YubiKey.

3. **Encrypt your age key**:
   ```bash
   nakimi yubikey encrypt-key
   ```
   **Important**: This encrypts your existing age private key with the YubiKey. A backup of the original key is created with `.backup` extension.

4. **Test decryption**:
   ```bash
   nakimi yubikey decrypt-key
   ```
   This verifies that the YubiKey can decrypt the encrypted key.

### Normal Operation

Once configured, YubiKey integration is transparent:

- **Encryption**: When you run `nakimi encrypt`, the age tool uses the encrypted private key
- **Decryption**: When you run `nakimi decrypt` or `nakimi session`, the YubiKey automatically decrypts the age key
- **PIN & Touch**: If configured, you'll be prompted for PIN and/or touch when needed

## Security Considerations

### Threat Model Enhancements

YubiKey integration improves security against these threats:

| Threat | Protection |
|--------|------------|
| **Stolen private key file** | Key is encrypted with YubiKey; unusable without hardware |
| **Malware on host** | Requires physical touch confirmation (if enabled) |
| **Unauthorized decryption** | Requires PIN + physical presence |
| **Key export** | YubiKey private key never leaves the hardware |

### Limitations

1. **Single YubiKey**: The age key is encrypted to a specific YubiKey. If you lose the YubiKey, you cannot decrypt your secrets without the backup.
2. **Backup critical**: Always keep the unencrypted age key backup in a secure location.
3. **Performance**: YubiKey operations add minimal overhead (typically < 1 second).
4. **Compatibility**: Only works with YubiKey 4/5 series with PIV support.

### Backup and Recovery

**Crucial**: Before enabling YubiKey, ensure you have a secure backup of your age private key.

**Recovery procedure if YubiKey is lost**:
1. Restore the original age key from backup:
   ```bash
   cp ~/.nakimi/key.txt.backup ~/.nakimi/key.txt
   ```
2. Disable YubiKey in configuration:
   ```bash
   export NAKIMI_YUBIKEY_ENABLED=false
   ```
3. Generate a new key pair if the backup is unavailable:
   ```bash
   nakimi init --force
   ```
   Note: This will make previously encrypted secrets inaccessible.

## Advanced Configuration

### Multiple YubiKeys

Nakimi currently supports a single YubiKey. For multiple YubiKey support, you would need to:

1. Encrypt the age key to multiple YubiKeys (not yet implemented)
2. Use a YubiKey management solution that supports key replication

### Custom PIV Configuration

If you need to use a different PIV slot or certificate:

1. Configure the slot using the `--slot` parameter during setup
2. Ensure the slot contains a valid key/certificate pair
3. Test with `nakimi yubikey status`

### Disabling Touch or PIN

For development or specific use cases, you can disable security features:

```bash
# Disable touch requirement
nakimi yubikey setup --no-touch

# Disable PIN prompt
nakimi yubikey setup --no-pin-prompt
```

**Security warning**: Disabling these features reduces security. Only disable for specific, controlled environments.

## Troubleshooting

### Common Issues

**"YubiKey not detected"**
- Ensure YubiKey is properly inserted
- Check USB connection
- Verify `ykman info` shows the YubiKey
- Check user permissions (may need udev rules on Linux)

**"PIN verification failed"**
- Default YubiKey PIV PIN is `123456`
- After 3 failed attempts, the PIN is blocked and requires PUK to unblock
- Use `ykman piv unblock-pin` to reset if blocked

**"Decryption failed"**
- Verify the age key was encrypted with the same YubiKey
- Check that the correct PIV slot is configured
- Ensure the YubiKey has the required certificate/key pair
- Test `age-plugin-yubikey --list --slot <slot>` to verify recipient generation
- Check `age-plugin-yubikey --identity --slot <slot>` for identity errors

**"ykman command not found"**
- Install yubikey-manager: `pip install yubikey-manager`
- Ensure `ykman` is in your PATH

**"age-plugin-yubikey command not found"**
- Install age-plugin-yubikey from [GitHub releases](https://github.com/str4d/age-plugin-yubikey/releases) or via cargo
- Ensure the binary is in your PATH (or `age-plugin-yubikey.exe` for WSL2)
- Run `age-plugin-yubikey --version` to verify installation
- For WSL2: Install the Windows binary and ensure it's in Windows PATH

### WSL2 Support

When using Windows Subsystem for Linux (WSL2), YubiKey access requires special configuration:

1. **USB Passthrough**: Use [USB/IP](https://learn.microsoft.com/en-us/windows/wsl/connect-usb) to pass the YubiKey through to WSL2.
2. **Windows Binary**: Alternatively, install `age-plugin-yubikey.exe` on Windows and ensure it's in your PATH. Nakimi will automatically detect the `.exe` binary from WSL2.
3. **PC/SC Service**: The `pcscd` service is not available in WSL2. Use the Windows binary approach.

**Diagnostics**: Run `nakimi yubikey status` to see WSL2 detection and plugin availability.

### Debug Mode

Enable verbose logging to debug YubiKey issues:

```bash
export NAKIMI_DEBUG=true
nakimi yubikey status
```

### Resetting Configuration

To disable YubiKey and return to standard age encryption:

```bash
# Disable YubiKey
export NAKIMI_YUBIKEY_ENABLED=false

# Restore original key from backup
cp ~/.nakimi/key.txt.backup ~/.nakimi/key.txt
```

## Implementation Details

### Technical Architecture

1. **Plugin Integration**: Uses `age-plugin-yubikey` for YubiKey operations (recipient/identity generation)
2. **Key Encryption**: Age private key is encrypted using standard age encryption with YubiKey recipient
3. **Key Storage**: Encrypted key is stored in `~/.nakimi/key.txt` (same location as plaintext key)
4. **Transparent Decryption**: Vault automatically detects encrypted keys and uses YubiKey identity via age-plugin-yubikey
5. **Secure Temp Files**: Decrypted keys are stored in RAM-backed temporary files with `mlock()` protection

### Encryption Format

The encrypted age key format uses standard age encryption with YubiKey recipients (via `age-plugin-yubikey`). The encrypted data is raw age-encrypted bytes, compatible with the `age` command-line tool.

**Mock Implementation**: For testing without hardware, `MockYubiKeyManager` uses a simple wrapper format: `MOCK:<base64-data>`.

### Mock Implementation for Testing

For development and testing without physical YubiKey hardware, Nakimi includes `MockYubiKeyManager`:

```python
from nakimi.core.yubikey import MockYubiKeyManager
from nakimi.core.config import VaultConfig

config = VaultConfig()
config.yubikey_enabled = True
yk = MockYubiKeyManager(config)

# Works without hardware
encrypted = yk.encrypt_age_key("AGE-SECRET-KEY-...")
decrypted = yk.decrypt_age_key(encrypted)
```

## Future Enhancements

Planned improvements for YubiKey integration:

1. **Multiple YubiKey support**: Encrypt to multiple YubiKeys for redundancy
2. **Smart card support**: Expand to other PIV-compatible smart cards
3. **OpenPGP integration**: Use YubiKey OpenPGP capabilities as alternative
4. **FIDO2/WebAuthn**: Support for modern FIDO2 authentication
5. **Backup encryption**: Encrypt age key backup with YubiKey as well

## Related Resources

- [YubiKey Manager Documentation](https://developers.yubico.com/yubikey-manager/)
- [PIV Technical Overview](https://developers.yubico.com/PIV/)
- [Age Encryption](https://age-encryption.org)
- [Nakimi Security Documentation](index.md)

---

*Last updated: 2026-02-01*