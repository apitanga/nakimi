"""
YubiKey integration for Nakimi.

Provides optional YubiKey support for encrypting age private keys
with YubiKey PIV slots (asymmetric encryption).

This module requires the `yubikey-manager` package (ykman) to be installed
and a YubiKey with PIV support (YubiKey 4/5 series).

Usage:
    from nakimi.core.yubikey import YubiKeyManager

    yk = YubiKeyManager(config)
    if yk.is_available():
        # Encrypt age private key with YubiKey
        encrypted_key = yk.encrypt_age_key(private_key_data)

        # Decrypt age private key (requires YubiKey + PIN/touch)
        private_key_data = yk.decrypt_age_key(encrypted_key)
"""

import logging
import os
import subprocess
from typing import Optional

from .config import VaultConfig

logger = logging.getLogger(__name__)


def is_wsl2() -> bool:
    """
    Detect if running in WSL2 (Windows Subsystem for Linux).

    Returns:
        True if running in WSL2, False otherwise.
    """
    # Check for WSL2 specific files
    try:
        # Method 1: Check /proc/version
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                return True
    except (FileNotFoundError, PermissionError):
        pass

    # Method 2: Check uname
    try:
        result = subprocess.run(["uname", "-r"], capture_output=True, text=True, check=False)
        if "microsoft" in result.stdout.lower():
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    # Method 3: Check environment variable
    if os.environ.get("WSL_DISTRO_NAME"):
        return True

    return False


class YubiKeyError(Exception):
    """Raised when YubiKey operations fail."""

    pass


class YubiKeyManager:
    """Manages YubiKey operations for age key encryption."""

    def __init__(self, config: VaultConfig):
        self.config = config
        self._ykman_available: Optional[bool] = None
        self._yubikey_present: Optional[bool] = None

    def _check_ykman_installed(self) -> bool:
        """Check if ykman CLI is available."""
        if self._ykman_available is not None:
            return self._ykman_available

        try:
            subprocess.run(["ykman", "--version"], capture_output=True, check=True)
            self._ykman_available = True
            logger.debug("ykman CLI detected")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._ykman_available = False
            logger.debug("ykman CLI not found")
            return False

    def _check_yubikey_present(self) -> bool:
        """Check if a YubiKey is present and accessible."""
        if self._yubikey_present is not None:
            return self._yubikey_present

        if not self._check_ykman_installed():
            self._yubikey_present = False
            return False

        try:
            result = subprocess.run(["ykman", "info"], capture_output=True, text=True, check=True)
            # If command succeeds, YubiKey is present
            self._yubikey_present = True
            logger.debug("YubiKey detected: %s", result.stdout[:100])
            return True
        except subprocess.CalledProcessError as e:
            # Could be no YubiKey present or other error
            logger.debug("YubiKey detection failed: %s", e.stderr)
            self._yubikey_present = False

            # Check for WSL2-specific error
            stderr = e.stderr or ""
            if "PC/SC not available" in stderr or "Smart card (CCID) protocols" in stderr:
                if is_wsl2():
                    logger.warning(
                        "YubiKey detection failed in WSL2. "
                        "PC/SC service is not available. "
                        "To use YubiKey in WSL2, you need to: "
                        "1. Install Windows YubiKey drivers "
                        "2. Set up USB passthrough "
                        "3. Configure PC/SC bridge "
                        "See: https://support.yubico.com/hc/en-us/articles/360013647640"
                    )
                else:
                    logger.warning(
                        "PC/SC service not available. "
                        "Make sure pcscd service is running: "
                        "sudo systemctl start pcscd"
                    )

            return False

    def _check_age_plugin_installed(self) -> bool:
        """Check if age-plugin-yubikey is available."""
        try:
            subprocess.run(["age-plugin-yubikey", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Also check for Windows binary in WSL2
            try:
                subprocess.run(
                    ["age-plugin-yubikey.exe", "--version"], capture_output=True, check=True
                )
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                return False

    def _get_yubikey_recipient(self) -> str:
        """
        Get age recipient string for the configured YubiKey slot.

        Runs: age-plugin-yubikey --list --slot <slot>
        """
        slot = self.config.yubikey_slot
        # Try age-plugin-yubikey, fall back to .exe for WSL2
        for cmd in ["age-plugin-yubikey", "age-plugin-yubikey.exe"]:
            try:
                result = subprocess.run(
                    [cmd, "--list", "--slot", slot], capture_output=True, text=True, check=True
                )
                # Parse output: recipient line starts with age1yubikey1...
                for line in result.stdout.split("\n"):
                    if line.startswith("age1yubikey1"):
                        return line.strip()
                raise YubiKeyError(f"No recipient found in {cmd} output")
            except FileNotFoundError:
                continue
            except subprocess.CalledProcessError as e:
                raise YubiKeyError(f"Failed to get recipient with {cmd}: {e.stderr}")
        raise YubiKeyError(
            "age-plugin-yubikey not found. "
            "Install it from https://github.com/str4d/age-plugin-yubikey"
        )

    def _get_yubikey_identity(self) -> str:
        """
        Get age identity for the configured YubiKey slot.

        Runs: age-plugin-yubikey --identity --slot <slot>
        Returns identity as string.
        """
        slot = self.config.yubikey_slot
        # Try age-plugin-yubikey, fall back to .exe for WSL2
        for cmd in ["age-plugin-yubikey", "age-plugin-yubikey.exe"]:
            try:
                result = subprocess.run(
                    [cmd, "--identity", "--slot", slot], capture_output=True, text=True, check=True
                )
                return result.stdout.strip()
            except FileNotFoundError:
                continue
            except subprocess.CalledProcessError as e:
                raise YubiKeyError(f"Failed to get identity with {cmd}: {e.stderr}")
        raise YubiKeyError(
            "age-plugin-yubikey not found. "
            "Install it from https://github.com/str4d/age-plugin-yubikey"
        )

    def is_available(self) -> bool:
        """
        Check if YubiKey support is available.

        Returns True if:
        1. YubiKey is enabled in config
        2. ykman CLI is installed
        3. A YubiKey is present and accessible
        """
        if not self.config.yubikey_enabled:
            return False

        if not self._check_ykman_installed():
            return False

        return self._check_yubikey_present()

    def get_diagnostics(self) -> dict:
        """
        Get detailed diagnostics about YubiKey setup.

        Returns:
            Dictionary with diagnostic information
        """
        diagnostics = {
            "yubikey_enabled": self.config.yubikey_enabled,
            "yubikey_slot": self.config.yubikey_slot,
            "ykman_installed": self._check_ykman_installed(),
            "age_plugin_installed": self._check_age_plugin_installed(),
            "wsl2_environment": is_wsl2(),
        }

        # Check YubiKey presence with detailed error
        ykman_installed = diagnostics["ykman_installed"]
        if ykman_installed:
            try:
                result = subprocess.run(
                    ["ykman", "info"],
                    capture_output=True,
                    text=True,
                    check=False,  # Don't raise exception
                )
                diagnostics["yubikey_detected"] = result.returncode == 0
                diagnostics["ykman_stdout"] = result.stdout.strip()
                diagnostics["ykman_stderr"] = result.stderr.strip()
                diagnostics["ykman_returncode"] = result.returncode

                # Check for specific error patterns
                if result.stderr:
                    if "PC/SC not available" in result.stderr:
                        diagnostics["pcsc_available"] = False
                        diagnostics["error_type"] = "pcsc_not_available"
                    else:
                        diagnostics["pcsc_available"] = True
            except Exception as e:
                diagnostics["yubikey_detected"] = False
                diagnostics["error"] = str(e)
        else:
            diagnostics["yubikey_detected"] = False

        return diagnostics

    def get_slot_info(self) -> dict:
        """
        Get information about the configured PIV slot.

        Returns:
            Dictionary with slot information (type, algorithm, etc.)
        """
        if not self.is_available():
            raise YubiKeyError("YubiKey not available")

        slot = self.config.yubikey_slot
        try:
            result = subprocess.run(
                ["ykman", "piv", "info", "slot", slot], capture_output=True, text=True, check=True
            )
            # Parse output (format varies)
            info = {}
            for line in result.stdout.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    info[key.strip()] = value.strip()
            return info
        except subprocess.CalledProcessError as e:
            raise YubiKeyError(f"Failed to get slot info: {e.stderr}")

    def export_public_key(self, slot: Optional[str] = None) -> str:
        """
        Export public key from YubiKey PIV slot.

        Args:
            slot: PIV slot (default: configured slot)

        Returns:
            PEM-encoded public key
        """
        if not self.is_available():
            raise YubiKeyError("YubiKey not available")

        slot = slot or self.config.yubikey_slot
        try:
            result = subprocess.run(
                ["ykman", "piv", "export-certificate", slot, "-"],
                capture_output=True,
                text=True,
                check=True,
            )
            # ykman outputs certificate, not just public key
            # We need to extract public key from certificate
            # For now, return certificate
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise YubiKeyError(f"Failed to export public key: {e.stderr}")

    def encrypt_with_yubikey(self, data: bytes, slot: Optional[str] = None) -> bytes:
        """
        Encrypt data using YubiKey's public key.

        Note: ykman doesn't directly support encryption.
        We need to use a different approach, possibly using
        openssl with the exported certificate.

        This is a placeholder implementation.
        """
        raise NotImplementedError(
            "Direct encryption with ykman not supported. "
            "Consider using openssl with exported certificate."
        )

    def decrypt_with_yubikey(self, encrypted_data: bytes, slot: Optional[str] = None) -> bytes:
        """
        Decrypt data using YubiKey's private key.

        Requires PIN and possibly touch.

        This is a placeholder implementation.
        """
        raise NotImplementedError(
            "Direct decryption with ykman not supported. "
            "Consider using openssl with YubiKey as PKCS#11 device."
        )

    def encrypt_age_key(self, age_private_key: str) -> bytes:
        """
        Encrypt age private key using YubiKey via age-plugin-yubikey.

        Args:
            age_private_key: Age private key as string

        Returns:
            Encrypted bytes

        Raises:
            YubiKeyError: If encryption fails
        """
        if not self._check_age_plugin_installed():
            raise YubiKeyError(
                "age-plugin-yubikey not installed. "
                "Install it from https://github.com/str4d/age-plugin-yubikey"
            )

        recipient = self._get_yubikey_recipient()

        try:
            result = subprocess.run(
                ["age", "-r", recipient],
                input=age_private_key.encode("utf-8"),
                capture_output=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise YubiKeyError(f"Age encryption failed: {e.stderr.decode()}")

    def decrypt_age_key(self, encrypted_key: bytes) -> str:
        """
        Decrypt age private key using YubiKey.

        This may require PIN entry and touch.

        Args:
            encrypted_key: Encrypted age key bytes

        Returns:
            Decrypted age private key as string

        Raises:
            YubiKeyError: If decryption fails or YubiKey is not available
        """
        import tempfile

        if not self._check_age_plugin_installed():
            raise YubiKeyError(
                "age-plugin-yubikey not installed. "
                "Install it from https://github.com/str4d/age-plugin-yubikey"
            )

        identity = self._get_yubikey_identity()

        # Write identity to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".age", delete=False) as f:
            f.write(identity)
            identity_file = f.name

        try:
            result = subprocess.run(
                ["age", "-d", "-i", identity_file],
                input=encrypted_key,
                capture_output=True,
                check=True,
            )
            return result.stdout.decode("utf-8")
        except subprocess.CalledProcessError as e:
            raise YubiKeyError(f"Age decryption failed: {e.stderr.decode()}")
        finally:
            # Clean up temporary file
            try:
                os.unlink(identity_file)
            except OSError:
                pass

    def verify_pin(self, pin: str) -> bool:
        """
        Verify PIN for YubiKey PIV application.

        Args:
            pin: PIN to verify

        Returns:
            True if PIN is correct
        """
        if not self.is_available():
            return False

        try:
            # ykman piv verify-pin command
            subprocess.run(
                ["ykman", "piv", "verify-pin", pin], capture_output=True, text=True, check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def change_pin(self, old_pin: str, new_pin: str) -> bool:
        """
        Change YubiKey PIV PIN.

        Args:
            old_pin: Current PIN
            new_pin: New PIN

        Returns:
            True if successful
        """
        if not self.is_available():
            return False

        try:
            subprocess.run(
                ["ykman", "piv", "change-pin", old_pin, new_pin],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False


class MockYubiKeyManager(YubiKeyManager):
    """Mock YubiKey manager for testing."""

    def __init__(self, config: VaultConfig, mock_present: bool = True):
        super().__init__(config)
        self.mock_present = mock_present
        self._ykman_available = True
        self._yubikey_present = mock_present
        self.mock_encrypted_keys = {}

    def _check_ykman_installed(self) -> bool:
        return True

    def _check_yubikey_present(self) -> bool:
        return self.mock_present

    def is_available(self) -> bool:
        return self.config.yubikey_enabled and self.mock_present

    def encrypt_age_key(self, age_private_key: str) -> bytes:
        """Mock encryption - just store key."""
        key_id = f"mock-key-{len(self.mock_encrypted_keys)}"
        self.mock_encrypted_keys[key_id] = age_private_key
        return f"MOCK:{key_id}".encode("utf-8")

    def decrypt_age_key(self, encrypted_key: bytes) -> str:
        """Mock decryption - retrieve stored key."""
        data = encrypted_key.decode("utf-8")
        if data.startswith("MOCK:"):
            key_id = data[5:]
            if key_id in self.mock_encrypted_keys:
                return self.mock_encrypted_keys[key_id]
        raise YubiKeyError("Mock key not found")

    def verify_pin(self, pin: str) -> bool:
        """Mock PIN verification."""
        return pin == "123456"  # Default mock PIN

    def change_pin(self, old_pin: str, new_pin: str) -> bool:
        """Mock PIN change."""
        return old_pin == "123456" and len(new_pin) >= 6
