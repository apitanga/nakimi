"""
Core vault operations - encryption/decryption with age
"""

import contextlib
import logging
import subprocess
import tempfile
import os
import platform
import ctypes
import mmap
from pathlib import Path
from typing import Optional, Union

# Optional YubiKey support
try:
    from .yubikey import YubiKeyManager

    YUBIKEY_AVAILABLE = True
except ImportError:
    YUBIKEY_AVAILABLE = False
    YubiKeyManager = None


class VaultCryptoError(Exception):
    """Raised when encryption/decryption operations fail"""

    pass


def can_mlock() -> bool:
    """Check if current user can use mlock to prevent swapping"""
    try:
        import resource

        soft, _ = resource.getrlimit(resource.RLIMIT_MEMLOCK)
        return soft > 0
    except (ImportError, OSError):
        return False


def get_mlock_limit() -> int:
    """Get maximum memory this user can lock (in bytes)"""
    try:
        import resource

        soft, _ = resource.getrlimit(resource.RLIMIT_MEMLOCK)
        return soft
    except (ImportError, OSError):
        return 0


def mlock_file(file_path: Union[str, Path]) -> bool:
    """
    Prevent a file from being swapped to disk using mlock.

    This locks the file's pages in RAM, preventing them from being
    written to swap even under memory pressure.

    Args:
        file_path: Path to file to lock in memory

    Returns:
        True if successful, False otherwise (no error raised)
    """
    if not can_mlock():
        return False

    try:
        path = Path(file_path)
        if not path.exists():
            return False

        # Get file size
        size = path.stat().st_size
        limit = get_mlock_limit()

        if size > limit:
            # File too large to lock
            return False

        # Memory map the file and lock it
        with open(path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, mmap.MAP_SHARED, mmap.PROT_READ) as mm:
                # Set up mlock call
                libc = ctypes.CDLL("libc.so.6")
                libc.mlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
                libc.mlock.restype = ctypes.c_int

                # Lock the memory
                addr = ctypes.c_void_p(ctypes.addressof(ctypes.c_char.from_buffer(mm)))
                result = libc.mlock(addr, mm.size())

                # Note: mmap will be unmapped when we exit 'with' block,
                # but the pages may stay locked in RAM until process exits
                return result == 0

    except Exception:
        return False


def get_secure_temp_dir() -> Optional[Path]:
    """
    Get the best available secure temp directory.

    Priority:
    1. /dev/shm (RAM - Linux, never hits disk)
    2. /private/tmp (RAM-backed on macOS)
    3. System temp (fallback - may hit disk)

    Returns None if no secure option available.
    """
    # Linux: /dev/shm is a RAM-backed tmpfs
    if platform.system() == "Linux":
        shm_path = Path("/dev/shm")
        if shm_path.exists() and shm_path.is_dir():
            # Check if we can write to it
            try:
                test_file = shm_path / ".nakimi-test"
                test_file.touch()
                test_file.unlink()
                return shm_path
            except (PermissionError, OSError):
                pass

    # macOS: /private/tmp is usually RAM-backed
    if platform.system() == "Darwin":
        mac_tmp = Path("/private/tmp")
        if mac_tmp.exists() and mac_tmp.is_dir():
            return mac_tmp

    # Fallback: None (use system default)
    return None


class Vault:
    """
    Core vault for managing encrypted secrets.

    This is the low-level encryption layer - no business logic,
    just encrypt/decrypt with age.
    """

    def __init__(
        self,
        key_file: Optional[Union[str, Path]] = None,
        vault_dir: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize vault.

        Args:
            key_file: Path to age private key (default: ~/.nakimi/key.txt)
            vault_dir: Directory for vault files (default: ~/.nakimi)
        """
        # Load config for defaults
        from .config import get_config

        config = get_config()
        self.config = config

        # Determine vault_dir
        if vault_dir is not None:
            vault_dir = Path(vault_dir).expanduser()
        elif key_file is not None:
            # vault_dir not provided, but key_file is -> derive from key_file
            vault_dir = Path(key_file).expanduser().parent
        else:
            # Neither provided, use config
            vault_dir = config.vault_dir

        # Determine key_file
        if key_file is not None:
            key_file = Path(key_file).expanduser()
        elif vault_dir is not None:
            # key_file not provided, but vault_dir is -> derive from vault_dir
            key_file = vault_dir / "key.txt"
        else:
            # Neither provided, use config
            key_file = config.key_file

        # Final assignments with fallbacks
        self.vault_dir = vault_dir if vault_dir else Path.home() / ".nakimi"
        self.key_file = key_file if key_file else self.vault_dir / "key.txt"
        self.key_pub_file = Path(str(self.key_file) + ".pub")

        # Initialize YubiKey manager if available and enabled
        self.yubikey_manager = None
        if YUBIKEY_AVAILABLE and config.yubikey_enabled:
            try:
                self.yubikey_manager = YubiKeyManager(config)
                # Check if YubiKey is actually available (hardware present)
                if not self.yubikey_manager.is_available():
                    self.yubikey_manager = None
                    logger = logging.getLogger(__name__)
                    logger.debug("YubiKey enabled in config but not available")
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to initialize YubiKey manager: {e}")
                self.yubikey_manager = None

    def _get_decrypted_key_path(self) -> Path:
        """
        Get path to decrypted age private key file.

        If YubiKey is enabled and key file is encrypted with YubiKey,
        decrypts it to a secure temporary file. Otherwise returns
        the original key file path.

        Returns:
            Path to key file that age can read

        Raises:
            VaultCryptoError if decryption fails
        """
        # Check if key file exists
        if not self.key_file.exists():
            raise VaultCryptoError(f"Private key not found: {self.key_file}")

        if not self.yubikey_manager:
            # No YubiKey manager - assume key file is plaintext
            return self.key_file

        # Read key file content
        with open(self.key_file, "rb") as f:
            key_data = f.read()

        # Try to parse as age key (look for AGE-SECRET-KEY- prefix)
        # If parsing fails, assume it's encrypted with YubiKey
        try:
            key_text = key_data.decode("utf-8")
            if "AGE-SECRET-KEY-" in key_text:
                # Already plaintext age key
                return self.key_file
        except UnicodeDecodeError:
            # Binary data - likely encrypted
            pass

        # Decrypt with YubiKey
        try:
            decrypted_key = self.yubikey_manager.decrypt_age_key(key_data)
        except Exception as e:
            raise VaultCryptoError(f"YubiKey decryption failed: {e}")

        # Create secure temporary file for decrypted key
        temp_dir = get_secure_temp_dir()
        if temp_dir:
            fd, temp_path = tempfile.mkstemp(prefix="nakimi-key-", suffix=".txt", dir=str(temp_dir))
        else:
            fd, temp_path = tempfile.mkstemp(prefix="nakimi-key-", suffix=".txt")
        os.close(fd)
        temp_path = Path(temp_path)

        # Write decrypted key
        with open(temp_path, "w") as f:
            f.write(decrypted_key)

        # Secure permissions
        os.chmod(temp_path, 0o600)

        # Try to lock in memory
        if temp_dir and can_mlock():
            mlock_file(temp_path)

        # Store reference for cleanup (could use atexit or context manager)
        # For now, caller must handle cleanup
        return temp_path

    @contextlib.contextmanager
    def _with_decrypted_key(self):
        """
        Context manager that yields a decrypted key file path.

        Ensures temporary key files are cleaned up after use.

        Yields:
            Path to decrypted key file
        """
        key_path = self._get_decrypted_key_path()
        try:
            yield key_path
        finally:
            # Clean up temporary key file if it's not the original key file
            if key_path != self.key_file and key_path.exists():
                # Use secure delete if possible
                secure_delete(key_path)

    def _check_age_installed(self):
        """Check if age is installed"""
        try:
            subprocess.run(["age", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise VaultCryptoError(
                "age is not installed. Install it from https://age-encryption.org"
            )

    def generate_key(self) -> str:
        """Generate a new age key pair"""
        self._check_age_installed()

        if self.key_file.exists():
            raise VaultCryptoError(
                f"Key file already exists: {self.key_file}\n"
                "Delete it first if you want to generate a new key."
            )

        # Ensure vault directory exists
        self.vault_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        try:
            result = subprocess.run(
                ["age-keygen", "-o", str(self.key_file)], capture_output=True, text=True, check=True
            )
            # Extract public key from stderr output
            public_key = None
            for line in result.stderr.split("\n"):
                if "public key:" in line:
                    public_key = line.split("public key:")[1].strip()
                    break

            # Also read from key file if not in stderr
            if not public_key:
                with open(self.key_file, "r") as f:
                    for line in f:
                        if line.startswith("# public key:"):
                            public_key = line.split(":")[1].strip()
                            break

            # Create .pub file
            if public_key:
                with open(self.key_pub_file, "w") as f:
                    f.write(public_key + "\n")

            # Secure the key file
            os.chmod(self.key_file, 0o600)

            return public_key

        except subprocess.CalledProcessError as e:
            raise VaultCryptoError(f"Failed to generate key: {e.stderr}")

    def get_public_key(self) -> str:
        """Get the public key from the .pub file or derive from private key"""
        if self.key_pub_file.exists():
            with open(self.key_pub_file, "r") as f:
                return f.read().strip()

        # Derive from private key
        if not self.key_file.exists():
            raise VaultCryptoError(f"Key file not found: {self.key_file}")

        with open(self.key_file, "r") as f:
            for line in f:
                if line.startswith("# public key:"):
                    return line.split(":")[1].strip()

        raise VaultCryptoError("Could not find public key")

    def encrypt(
        self,
        plaintext_path: Union[str, Path],
        ciphertext_path: Optional[Union[str, Path]] = None,
        recipient: Optional[str] = None,
    ) -> Path:
        """
        Encrypt a file using age.

        Args:
            plaintext_path: File to encrypt
            ciphertext_path: Output file (default: input + ".age")
            recipient: Public key to encrypt to (default: self)

        Returns:
            Path to encrypted file
        """
        self._check_age_installed()

        input_path = Path(plaintext_path).expanduser()
        if not input_path.exists():
            raise VaultCryptoError(f"Input file not found: {input_path}")

        if ciphertext_path is None:
            output_path = Path(str(input_path) + ".age")
        else:
            output_path = Path(ciphertext_path).expanduser()

        pub_key = recipient or self.get_public_key()

        try:
            subprocess.run(
                ["age", "-r", pub_key, "-o", str(output_path), str(input_path)],
                capture_output=True,
                check=True,
            )
            return output_path
        except subprocess.CalledProcessError as e:
            raise VaultCryptoError(f"Encryption failed: {e.stderr.decode()}")

    def decrypt(
        self, ciphertext_path: Union[str, Path], plaintext_path: Optional[Union[str, Path]] = None
    ) -> Path:
        """
        Decrypt a file using age.

        Args:
            ciphertext_path: File to decrypt (.age file)
            plaintext_path: Output file (default: secure tempfile)

        Returns:
            Path to decrypted file
        """
        self._check_age_installed()

        input_path = Path(ciphertext_path).expanduser()
        if not input_path.exists():
            raise VaultCryptoError(f"Encrypted file not found: {input_path}")

        using_ram_temp = False

        if plaintext_path is None:
            # Create secure temp file in RAM if possible
            temp_dir = get_secure_temp_dir()
            if temp_dir:
                # Use RAM-backed temp directory
                fd, output_path = tempfile.mkstemp(
                    prefix="nakimi-secrets-", suffix=".json", dir=str(temp_dir)
                )
                os.close(fd)
                output_path = Path(output_path)
                using_ram_temp = True
            else:
                # Fallback to system temp
                fd, output_path = tempfile.mkstemp(prefix="nakimi-secrets-", suffix=".json")
                os.close(fd)
                output_path = Path(output_path)
        else:
            output_path = Path(plaintext_path).expanduser()

        try:
            with self._with_decrypted_key() as key_path:
                subprocess.run(
                    ["age", "-d", "-i", str(key_path), "-o", str(output_path), str(input_path)],
                    capture_output=True,
                    check=True,
                )
            # Secure the temp file
            os.chmod(output_path, 0o600)

            # Try to lock in memory to prevent swapping (best effort)
            if using_ram_temp and can_mlock():
                # We have a RAM-based file and can mlock - try to prevent swap
                if not mlock_file(output_path):
                    # mlock failed, but we still have RAM storage
                    pass  # Silent - this is an optimization

            return output_path
        except subprocess.CalledProcessError as e:
            # Clean up temp file on failure
            if plaintext_path is None and output_path.exists():
                output_path.unlink()
            raise VaultCryptoError(f"Decryption failed: {e.stderr.decode()}")

    def decrypt_to_string(self, ciphertext_path: Union[str, Path]) -> str:
        """
        Decrypt a file and return contents as string.

        Warning: Be careful - secrets will be in memory.
        """
        self._check_age_installed()

        input_path = Path(ciphertext_path).expanduser()
        if not input_path.exists():
            raise VaultCryptoError(f"Encrypted file not found: {input_path}")

        try:
            with self._with_decrypted_key() as key_path:
                result = subprocess.run(
                    ["age", "-d", "-i", str(key_path), str(input_path)],
                    capture_output=True,
                    check=True,
                )
            return result.stdout.decode("utf-8")
        except subprocess.CalledProcessError as e:
            raise VaultCryptoError(f"Decryption failed: {e.stderr.decode()}")


def is_ram_disk(path: Union[str, Path]) -> bool:
    """Check if path is on a RAM-backed filesystem (tmpfs)"""
    try:
        result = subprocess.run(["df", "-T", str(path)], capture_output=True, text=True, check=True)
        return "tmpfs" in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def secure_delete(file_path: Union[str, Path]):
    """
    Securely delete a file.

    If the file is on a RAM disk (tmpfs), regular delete is sufficient
    since the data was never on physical disk.

    Otherwise, use shred to overwrite before deleting (best effort on SSDs).
    """
    path = Path(file_path).expanduser()
    if not path.exists():
        return

    # Check if on RAM disk
    if is_ram_disk(path):
        # On RAM disk - regular delete is sufficient
        # Data was never on physical storage
        path.unlink()
        return

    # On physical storage - try shred first
    try:
        subprocess.run(["shred", "-u", str(path)], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall back to regular delete
        path.unlink()
