"""
Main CLI entry point for Nakimi

Provides plugin-based command execution and vault management.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from nakimi.core import Vault, get_config, secure_delete
from nakimi.core.plugin import PluginManager, PluginError

# Optional YubiKey support
try:
    from nakimi.core.yubikey import YubiKeyManager, YubiKeyError, is_wsl2

    YUBIKEY_AVAILABLE = True
except ImportError:
    YUBIKEY_AVAILABLE = False
    YubiKeyManager = None
    YubiKeyError = Exception

    def is_wsl2():
        return False


# Version - sync with pyproject.toml
__version__ = "2.0.0"


def get_secrets_path() -> Path:
    """Get secrets file path from env or config"""
    # Priority: NAKIMI_SECRETS > NAKIMI_BOT_SECRETS > config default
    env_path = os.environ.get("NAKIMI_SECRETS") or os.environ.get("NAKIMI_BOT_SECRETS")
    if env_path:
        return Path(env_path)

    config = get_config()
    return config.secrets_file


def load_secrets() -> dict:
    """Load and parse secrets JSON"""
    secrets_path = get_secrets_path()

    if not secrets_path.exists():
        raise PluginError(
            f"No secrets file found at {secrets_path}\n" "Run 'nakimi init' to set up your vault."
        )

    # Check if file is encrypted (.age extension)
    if str(secrets_path).endswith(".age"):
        # Need to decrypt first
        vault = Vault()
        temp_path = vault.decrypt(secrets_path)
        try:
            with open(temp_path, "r") as f:
                return json.load(f)
        finally:
            secure_delete(temp_path)
    else:
        # Plaintext JSON
        with open(secrets_path, "r") as f:
            return json.load(f)


def cmd_init(args):
    """Initialize vault and generate keys"""
    config = get_config()
    config.ensure_directories()

    vault = Vault()

    if vault.key_file.exists():
        print(f"✅ Key already exists: {vault.key_file}")
        print(f"   Public key: {vault.get_public_key()}")
    else:
        print("🔐 Generating new age key pair...")
        public_key = vault.generate_key()
        print("✅ Key generated!")
        print(f"   Private key: {vault.key_file}")
        print(f"   Public key: {public_key}")
        print()
        print("⚠️  IMPORTANT: Back up your private key to a secure location!")
        print("   If you lose this key, you CANNOT decrypt your secrets.")


def cmd_encrypt(args):
    """Encrypt a file"""
    vault = Vault()

    input_file = Path(args.file)
    if not input_file.exists():
        print(f"❌ File not found: {input_file}")
        sys.exit(1)

    output_file = args.output or f"{input_file}.age"

    print(f"🔐 Encrypting {input_file}...")
    result = vault.encrypt(input_file, output_file)
    print(f"✅ Encrypted to: {result}")

    if args.shred:
        print("🧹 Securely deleting original...")
        secure_delete(input_file)


def cmd_decrypt(args):
    """Decrypt a file"""
    vault = Vault()

    input_file = Path(args.file)
    if not input_file.exists():
        print(f"❌ File not found: {input_file}")
        sys.exit(1)

    output_file = args.output

    print(f"🔓 Decrypting {input_file}...")
    result = vault.decrypt(input_file, output_file)
    print(f"✅ Decrypted to: {result}")

    if not args.keep:
        print("⚠️  Warning: Use --keep to preserve decrypted file, or it will be temporary.")


def cmd_plugins(args):
    """List available plugins"""
    try:
        secrets = load_secrets()
    except PluginError as e:
        print(f"⚠️  {e}")
        secrets = {}

    manager = PluginManager(secrets)

    # Auto-discover plugins
    manager.discover_plugins()

    if args.command == "list":
        plugins = manager.list_plugins()
        if plugins:
            print("Loaded plugins:")
            for name in plugins:
                plugin = manager.get_plugin(name)
                print(f"  • {name:15} - {plugin.description}")
        else:
            print("No plugins loaded.")
            print("Add credentials to your secrets.json to enable plugins.")

    elif args.command == "commands":
        commands = manager.list_commands()
        if commands:
            print("Available commands:")
            for cmd in sorted(commands):
                print(f"  {cmd}")
        else:
            print("No commands available.")


def cmd_run(args):
    """Run a plugin command"""
    try:
        secrets = load_secrets()
    except PluginError as e:
        print(f"❌ {e}")
        sys.exit(1)

    manager = PluginManager(secrets)
    manager.discover_plugins()

    full_command = f"{args.plugin}.{args.command}"

    try:
        result = manager.execute_command(full_command, args.args)
        if result:
            print(result)
    except PluginError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_serve(args):
    """Start MCP server for AI assistant integration"""
    try:
        from nakimi.mcp_server import run_server
    except ImportError:
        print("MCP server requires the 'mcp' package.")
        print("Install with: pip install nakimi[mcp]")
        sys.exit(1)
    run_server()


def cmd_upgrade(args):
    """Upgrade nakimi to latest version from GitHub"""
    repo_url = "https://github.com/apitanga/nakimi.git"

    print("🔄 Upgrading nakimi...")
    print(f"   Repository: {repo_url}")
    if args.target_version:
        print(f"   Target version: {args.target_version}")
    else:
        print("   Target: latest main branch")
    print()

    # Construct pip install command
    if args.target_version:
        install_spec = f"git+{repo_url}@{args.target_version}"
    else:
        install_spec = f"git+{repo_url}"

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", install_spec]

    print(f"Running: pip install --upgrade {install_spec}")
    print()

    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode == 0:
            print()
            print("✅ Upgrade complete!")
            print()
            # Show new version
            print("New version:")
            subprocess.run([sys.executable, "-m", "nakimi.cli.main", "--version"])
        else:
            print()
            print(f"❌ Upgrade failed with exit code {result.returncode}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error during upgrade: {e}")
        sys.exit(1)


def cmd_version():
    """Show version information"""
    print(f"nakimi {__version__}")
    print(f"Python {sys.version.split()[0]}")
    print(f"Location: {Path(__file__).parent.parent.parent}")


def cmd_session(args):  # noqa: C901
    """Start a secure session with decrypted secrets"""
    import subprocess

    config = get_config()
    vault = Vault()

    # Check vault exists
    if not config.secrets_file.exists():
        print(f"❌ No encrypted secrets found at {config.secrets_file}")
        print("Run 'nakimi init' to set up your vault.")
        sys.exit(1)

    # Decrypt secrets to temp file
    print("🔓 Decrypting vault...")
    try:
        temp_secrets = vault.decrypt(config.secrets_file)
    except Exception as e:
        print(f"❌ Failed to decrypt: {e}")
        sys.exit(1)

    print("✅ Vault decrypted")
    print()

    # Show available plugins
    try:
        with open(temp_secrets, "r") as f:
            secrets = json.load(f)
        manager = PluginManager(secrets)
        manager.discover_plugins()

        if manager.list_plugins():
            print("Available plugins:")
            for name in manager.list_plugins():
                plugin = manager.get_plugin(name)
                print(f"  ✅ {name} - {plugin.description}")
        else:
            print("⚠️  No plugins configured")
    except Exception:
        pass

    print()
    print("💡 Usage: nakimi <plugin>.<command> [args]")
    print("         Example: nakimi gmail.unread")
    print()

    # Set up cleanup
    def cleanup():
        if temp_secrets.exists():
            secure_delete(temp_secrets)
            print("\n🔒 Vault closed")

    # Export secrets path
    os.environ["NAKIMI_SECRETS"] = str(temp_secrets)

    try:
        # Launch shell or kimi
        if args.shell:
            subprocess.run([os.environ.get("SHELL", "/bin/bash")])
        elif args.command:
            # Run specific command
            result = subprocess.run(args.command)
            cleanup()
            sys.exit(result.returncode)
        else:
            # Try to launch kimi, fall back to shell
            try:
                subprocess.run(["kimi"])
            except FileNotFoundError:
                print("kimi not found, starting shell...")
                subprocess.run([os.environ.get("SHELL", "/bin/bash")])
    finally:
        cleanup()


def cmd_yubikey(args):  # noqa: C901
    """Handle YubiKey commands"""
    if not YUBIKEY_AVAILABLE:
        print("❌ YubiKey support not available")
        print("   Install with: pip install yubikey-manager")
        sys.exit(1)

    config = get_config()

    if not args.yubikey_command:
        print("❌ No yubikey command specified")
        print("   Available commands: setup, status, encrypt-key, decrypt-key, verify-pin, change-pin")
        sys.exit(1)

    try:
        yk = YubiKeyManager(config)

        if args.yubikey_command == "setup":
            print("🔧 Setting up YubiKey for Nakimi...")

            # Check if YubiKey is available
            if not yk.is_available():
                print("❌ YubiKey not detected")
                print("   Make sure:")
                print("   1. ykman CLI is installed (pip install yubikey-manager)")
                print("   2. YubiKey is inserted")
                print("   3. You have appropriate permissions")
                sys.exit(1)

            # Get slot info
            try:
                slot_info = yk.get_slot_info()
                print("✅ YubiKey detected")
                print(f"   Slot {args.slot}: {slot_info.get('Algorithm', 'Unknown algorithm')}")
            except YubiKeyError as e:
                print(f"⚠️  Could not read slot info: {e}")
                print("   The slot may not be initialized")

            # Update configuration
            import os

            os.environ["NAKIMI_YUBIKEY_ENABLED"] = "true"
            os.environ["NAKIMI_YUBIKEY_SLOT"] = args.slot
            os.environ["NAKIMI_YUBIKEY_REQUIRE_TOUCH"] = "false" if args.no_touch else "true"
            os.environ["NAKIMI_YUBIKEY_PIN_PROMPT"] = "false" if args.no_pin_prompt else "true"

            print("✅ Configuration updated")
            print("   YubiKey will be used for age key encryption")
            print("   Note: age-plugin-yubikey must be installed for encryption/decryption")
            print()
            print("⚠️  IMPORTANT: Run 'nakimi yubikey encrypt-key' " "to encrypt your existing age key")

        elif args.yubikey_command == "status":
            print("🔍 Checking YubiKey status...")

            # Check ykman
            if not yk._check_ykman_installed():
                print("❌ ykman CLI not found")
                print("   Install with: pip install yubikey-manager")
                sys.exit(1)

            # Check YubiKey
            if not yk._check_yubikey_present():
                print("❌ No YubiKey detected")
                print("   Make sure YubiKey is inserted")
                sys.exit(1)

            print("✅ YubiKey detected")

            # Check age-plugin-yubikey
            if not yk._check_age_plugin_installed():
                print("⚠️  age-plugin-yubikey not found")
                print("   Install from: https://github.com/str4d/age-plugin-yubikey")
                if is_wsl2():
                    print("   For WSL2: Install Windows binary (age-plugin-yubikey.exe)")
            else:
                print("✅ age-plugin-yubikey installed")

            # Check configuration
            print("\n📋 Configuration:")
            print(f"   Enabled: {config.yubikey_enabled}")
            print(f"   Slot: {config.yubikey_slot}")
            print(f"   Require touch: {config.yubikey_require_touch}")
            print(f"   PIN prompt: {config.yubikey_pin_prompt}")

            # Try to get slot info
            try:
                slot_info = yk.get_slot_info()
                print(f"\n🔑 Slot {config.yubikey_slot} info:")
                for key, value in slot_info.items():
                    print(f"   {key}: {value}")
            except YubiKeyError as e:
                print(f"\n⚠️  Could not read slot info: {e}")

        elif args.yubikey_command == "encrypt-key":
            print("🔐 Encrypting age key with YubiKey...")

            vault = Vault()

            # Check if key exists
            if not vault.key_file.exists():
                print(f"❌ Age key not found: {vault.key_file}")
                print("   Run 'nakimi init' first to generate a key")
                sys.exit(1)

            # Read current key
            with open(vault.key_file, "r") as f:
                age_key = f.read()

            # Encrypt with YubiKey
            try:
                encrypted_key = yk.encrypt_age_key(age_key)
            except Exception as e:
                print(f"❌ Encryption failed: {e}")
                sys.exit(1)

            # Backup original key
            backup_path = vault.key_file.with_suffix(".txt.backup")
            import shutil

            shutil.copy2(vault.key_file, backup_path)
            print(f"✅ Original key backed up to: {backup_path}")

            # Write encrypted key
            with open(vault.key_file, "wb") as f:
                f.write(encrypted_key)

            print("✅ Age key encrypted with YubiKey")
            print(f"   Encrypted key saved to: {vault.key_file}")
            print("   Keep backup safe in case YubiKey is lost")

        elif args.yubikey_command == "decrypt-key":
            print("🔓 Testing YubiKey decryption...")

            vault = Vault()

            # Check if key exists
            if not vault.key_file.exists():
                print(f"❌ Key file not found: {vault.key_file}")
                sys.exit(1)

            # Read encrypted key
            with open(vault.key_file, "rb") as f:
                encrypted_key = f.read()

            # Try to decrypt
            try:
                decrypted_key = yk.decrypt_age_key(encrypted_key)
                print("✅ Decryption successful")
                print(f"   Key type: {'age' if 'AGE-SECRET-KEY-' in decrypted_key else 'unknown'}")
                print(f"   Key length: {len(decrypted_key)} chars")
            except Exception as e:
                print(f"❌ Decryption failed: {e}")
                sys.exit(1)

        elif args.yubikey_command == "verify-pin":
            print("🔒 Verifying PIN...")

            if not yk.is_available():
                print("❌ YubiKey not available")
                sys.exit(1)

            if yk.verify_pin(args.pin):
                print("✅ PIN verified successfully")
            else:
                print("❌ PIN verification failed")
                sys.exit(1)

        elif args.yubikey_command == "change-pin":
            print("🔒 Changing PIN...")

            if not yk.is_available():
                print("❌ YubiKey not available")
                sys.exit(1)

            if yk.change_pin(args.old_pin, args.new_pin):
                print("✅ PIN changed successfully")
            else:
                print("❌ PIN change failed")
                print("   Make sure old PIN is correct")
                sys.exit(1)

        else:
            print(f"❌ Unknown yubikey command: {args.yubikey_command}")
            sys.exit(1)

    except YubiKeyError as e:
        print(f"❌ YubiKey error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    # Check for plugin command BEFORE setting up argparse
    # This allows plugin commands like "gmail.unread" to work
    if len(sys.argv) > 1 and "." in sys.argv[1] and not sys.argv[1].startswith("-"):
        plugin_cmd = sys.argv[1]
        if "." in plugin_cmd:
            parts = plugin_cmd.split(".", 1)

            # Create minimal args object for cmd_run
            class Args:
                pass

            args = Args()
            args.plugin = parts[0]
            args.command = parts[1]
            args.args = sys.argv[2:]
            return cmd_run(args)

    parser = argparse.ArgumentParser(
        prog="nakimi",
        description="Secure vault for API credentials with plugin-based integrations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s init                          # Initialize vault
  %(prog)s session                       # Start secure session
  %(prog)s gmail.unread                  # List unread emails
  %(prog)s gmail.search "from:boss"      # Search emails
  %(prog)s plugins list                  # List available plugins
  %(prog)s upgrade                       # Upgrade to latest version

YubiKey commands (optional):
  %(prog)s yubikey setup                 # Initialize YubiKey
  %(prog)s yubikey status                # Check YubiKey status
  %(prog)s yubikey encrypt-key           # Encrypt age key with YubiKey
        """,
    )

    # Add version flag
    parser.add_argument("--version", "-v", action="store_true", help="Show version information")

    subparsers = parser.add_subparsers(dest="cmd", help="Commands")

    # init command
    subparsers.add_parser("init", help="Initialize vault and generate keys")

    # encrypt command
    encrypt_parser = subparsers.add_parser("encrypt", help="Encrypt a file")
    encrypt_parser.add_argument("file", help="File to encrypt")
    encrypt_parser.add_argument("-o", "--output", help="Output file")
    encrypt_parser.add_argument(
        "--shred", action="store_true", help="Securely delete original after encryption"
    )

    # decrypt command
    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt a file")
    decrypt_parser.add_argument("file", help="File to decrypt")
    decrypt_parser.add_argument("-o", "--output", help="Output file")
    decrypt_parser.add_argument("--keep", action="store_true", help="Keep decrypted file")

    # plugins command
    plugins_parser = subparsers.add_parser("plugins", help="Manage plugins")
    plugins_sub = plugins_parser.add_subparsers(dest="command", help="Plugin commands")
    plugins_sub.add_parser("list", help="List available plugins")
    plugins_sub.add_parser("commands", help="List available commands")

    # session command
    session_parser = subparsers.add_parser("session", help="Start secure session")
    session_parser.add_argument("--shell", action="store_true", help="Start shell instead of kimi")
    session_parser.add_argument(
        "--exec", dest="command", nargs=argparse.REMAINDER, help="Execute command and exit"
    )

    # yubikey command
    yubikey_parser = subparsers.add_parser("yubikey", help="YubiKey management and operations")
    yubikey_sub = yubikey_parser.add_subparsers(dest="yubikey_command", help="YubiKey commands")

    # yubikey setup
    setup_parser = yubikey_sub.add_parser("setup", help="Initialize YubiKey for use with Nakimi")
    setup_parser.add_argument("--slot", default="9a", help="PIV slot to use (default: 9a)")
    setup_parser.add_argument("--no-touch", action="store_true", help="Disable touch requirement")
    setup_parser.add_argument("--no-pin-prompt", action="store_true", help="Disable PIN prompt")

    # yubikey status
    yubikey_sub.add_parser("status", help="Check YubiKey status and configuration")

    # yubikey encrypt-key
    encrypt_parser = yubikey_sub.add_parser("encrypt-key", help="Encrypt existing age key with YubiKey")
    encrypt_parser.add_argument("--slot", default="9a", help="PIV slot to use (default: 9a)")

    # yubikey decrypt-key (for testing)
    yubikey_sub.add_parser("decrypt-key", help="Decrypt age key (for testing)")

    # yubikey verify-pin
    verify_parser = yubikey_sub.add_parser("verify-pin", help="Verify YubiKey PIN")
    verify_parser.add_argument("pin", help="PIN to verify")

    # yubikey change-pin
    change_parser = yubikey_sub.add_parser("change-pin", help="Change YubiKey PIN")
    change_parser.add_argument("old_pin", help="Current PIN")
    change_parser.add_argument("new_pin", help="New PIN")

    # serve command (MCP server)
    subparsers.add_parser("serve", help="Start MCP server for AI assistant integration")

    # upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade to latest version from GitHub")
    upgrade_parser.add_argument(
        "--version", dest="target_version", help="Specific version to upgrade to (default: latest)"
    )

    # plugin command (direct invocation: nakimi gmail.unread)
    # This is handled specially below

    args, remaining = parser.parse_known_args()

    # Handle --version flag
    if args.version:
        cmd_version()
        sys.exit(0)

    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    # Route to appropriate handler
    handlers = {
        "init": cmd_init,
        "encrypt": cmd_encrypt,
        "decrypt": cmd_decrypt,
        "plugins": cmd_plugins,
        "session": cmd_session,
        "upgrade": cmd_upgrade,
        "serve": cmd_serve,
        "yubikey": cmd_yubikey,
    }

    handler = handlers.get(args.cmd)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
