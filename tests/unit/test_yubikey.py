"""
Unit tests for yubikey.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from nakimi.core.yubikey import YubiKeyManager, MockYubiKeyManager, YubiKeyError
from nakimi.core.config import VaultConfig


class TestYubiKeyManager:
    """Test YubiKeyManager class."""

    def setup_method(self):
        """Reset config before each test."""
        import os

        os.environ["NAKIMI_YUBIKEY_ENABLED"] = "false"
        os.environ["NAKIMI_YUBIKEY_SLOT"] = "9a"
        os.environ["NAKIMI_YUBIKEY_REQUIRE_TOUCH"] = "true"
        os.environ["NAKIMI_YUBIKEY_PIN_PROMPT"] = "true"

    def test_init_with_default_config(self):
        """Test YubiKeyManager initialization."""
        config = VaultConfig()
        yk = YubiKeyManager(config)
        assert yk.config == config
        assert yk._ykman_available is None
        assert yk._yubikey_present is None

    def test_check_ykman_installed_found(self):
        """Test ykman installed detection when available."""
        config = VaultConfig()
        yk = YubiKeyManager(config)

        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = yk._check_ykman_installed()
            assert result is True
            mock_run.assert_called_once_with(["ykman", "--version"], capture_output=True, check=True)
            # Second call should use cached value
            result2 = yk._check_ykman_installed()
            assert result2 is True
            # Should still be only one call due to caching
            assert mock_run.call_count == 1

    def test_check_ykman_installed_not_found(self):
        """Test ykman installed detection when not available."""
        config = VaultConfig()
        yk = YubiKeyManager(config)

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = yk._check_ykman_installed()
            assert result is False
            # Check caching
            result2 = yk._check_ykman_installed()
            assert result2 is False

    def test_check_yubikey_present_no_ykman(self):
        """Test YubiKey presence detection when ykman not installed."""
        config = VaultConfig()
        yk = YubiKeyManager(config)

        # Mock ykman not installed
        with patch.object(yk, "_check_ykman_installed", return_value=False):
            result = yk._check_yubikey_present()
            assert result is False
            # Should cache the result
            assert yk._yubikey_present is False

    def test_check_yubikey_present_with_ykman(self):
        """Test YubiKey presence detection when ykman is installed."""
        config = VaultConfig()
        yk = YubiKeyManager(config)

        # Mock ykman installed and YubiKey present
        with patch.object(yk, "_check_ykman_installed", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "YubiKey 5 NFC [5.7.1]"
                mock_run.return_value = mock_result

                result = yk._check_yubikey_present()
                assert result is True
                mock_run.assert_called_once_with(
                    ["ykman", "info"], capture_output=True, text=True, check=True
                )

    def test_check_yubikey_present_error(self):
        """Test YubiKey presence detection when ykman command fails."""
        import subprocess

        config = VaultConfig()
        yk = YubiKeyManager(config)

        with patch.object(yk, "_check_ykman_installed", return_value=True):
            with patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ykman info", stderr="No YubiKey"),
            ):
                result = yk._check_yubikey_present()
                assert result is False

    def test_is_available_disabled_in_config(self):
        """Test is_available when YubiKey disabled in config."""
        config = VaultConfig()
        config._yubikey_enabled = False
        yk = YubiKeyManager(config)

        # Even if ykman is installed and YubiKey present
        with patch.object(yk, "_check_ykman_installed", return_value=True):
            with patch.object(yk, "_check_yubikey_present", return_value=True):
                result = yk.is_available()
                assert result is False

    def test_is_available_enabled_but_no_ykman(self):
        """Test is_available when enabled but ykman not installed."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        with patch.object(yk, "_check_ykman_installed", return_value=False):
            result = yk.is_available()
            assert result is False

    def test_is_available_enabled_and_yubikey_present(self):
        """Test is_available when enabled, ykman installed, and YubiKey present."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        with patch.object(yk, "_check_ykman_installed", return_value=True):
            with patch.object(yk, "_check_yubikey_present", return_value=True):
                result = yk.is_available()
                assert result is True

    def test_encrypt_age_key(self):
        """Test encrypt_age_key with mocked age-plugin-yubikey."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        # Mock is_available to return True
        with patch.object(yk, "is_available", return_value=True):
            with patch.object(yk, "_check_age_plugin_installed", return_value=True):
                with patch.object(yk, "_get_yubikey_recipient", return_value="age1yubikey1testrecipient"):
                    with patch("subprocess.run") as mock_run:
                        mock_result = Mock()
                        mock_result.stdout = b"ENCRYPTED_DATA"
                        mock_result.returncode = 0
                        mock_run.return_value = mock_result

                        encrypted = yk.encrypt_age_key("AGE-SECRET-KEY-1TEST123")
                        assert encrypted == b"ENCRYPTED_DATA"
                        mock_run.assert_called_once_with(
                            ["age", "-r", "age1yubikey1testrecipient"],
                            input=b"AGE-SECRET-KEY-1TEST123",
                            capture_output=True,
                            check=True,
                        )

    def test_decrypt_age_key(self):
        """Test decrypt_age_key with mocked age-plugin-yubikey."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        # Mock is_available to return True
        with patch.object(yk, "is_available", return_value=True):
            with patch.object(yk, "_check_age_plugin_installed", return_value=True):
                with patch.object(yk, "_get_yubikey_identity", return_value="AGE-SECRET-KEY-1TESTIDENTITY"):
                    with patch("tempfile.NamedTemporaryFile") as mock_temp:
                        mock_file = MagicMock()
                        mock_file.name = "/tmp/mock.age"
                        mock_file.__enter__.return_value = mock_file
                        mock_file.__exit__.return_value = None
                        mock_temp.return_value = mock_file
                        with patch("subprocess.run") as mock_run:
                            mock_result = Mock()
                            mock_result.stdout = b"DECRYPTED_DATA"
                            mock_result.returncode = 0
                            mock_run.return_value = mock_result
                            with patch("os.unlink") as mock_unlink:
                                decrypted = yk.decrypt_age_key(b"ENCRYPTED_DATA")
                                assert decrypted == "DECRYPTED_DATA"
                                mock_file.write.assert_called_once_with("AGE-SECRET-KEY-1TESTIDENTITY")
                                mock_run.assert_called_once_with(
                                    ["age", "-d", "-i", "/tmp/mock.age"],
                                    input=b"ENCRYPTED_DATA",
                                    capture_output=True,
                                    check=True,
                                )
                                mock_unlink.assert_called_once_with("/tmp/mock.age")
                                mock_file.__exit__.assert_called_once()

    def test_verify_pin_yubikey_not_available(self):
        """Test verify_pin when YubiKey not available."""
        config = VaultConfig()
        config._yubikey_enabled = False
        yk = YubiKeyManager(config)

        result = yk.verify_pin("123456")
        assert result is False

    def test_verify_pin_success(self):
        """Test verify_pin success scenario."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        with patch.object(yk, "is_available", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_run.return_value = mock_result

                result = yk.verify_pin("123456")
                assert result is True
                mock_run.assert_called_once_with(
                    ["ykman", "piv", "verify-pin", "123456"],
                    capture_output=True,
                    text=True,
                    check=True,
                )

    def test_verify_pin_failure(self):
        """Test verify_pin failure scenario."""
        import subprocess

        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        with patch.object(yk, "is_available", return_value=True):
            with patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ykman piv verify-pin", stderr="Wrong PIN"),
            ):
                result = yk.verify_pin("wrong")
                assert result is False

    def test_change_pin_yubikey_not_available(self):
        """Test change_pin when YubiKey not available."""
        config = VaultConfig()
        config._yubikey_enabled = False
        yk = YubiKeyManager(config)

        result = yk.change_pin("old", "new")
        assert result is False

    def test_change_pin_success(self):
        """Test change_pin success scenario."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        with patch.object(yk, "is_available", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_run.return_value = mock_result

                result = yk.change_pin("123456", "654321")
                assert result is True
                mock_run.assert_called_once_with(
                    ["ykman", "piv", "change-pin", "123456", "654321"],
                    capture_output=True,
                    text=True,
                    check=True,
                )

    def test_change_pin_failure(self):
        """Test change_pin failure scenario."""
        import subprocess

        config = VaultConfig()
        config._yubikey_enabled = True
        yk = YubiKeyManager(config)

        with patch.object(yk, "is_available", return_value=True):
            with patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ykman piv change-pin", stderr="Wrong old PIN"),
            ):
                result = yk.change_pin("wrong", "new")
                assert result is False


class TestMockYubiKeyManager:
    """Test MockYubiKeyManager class."""

    def test_mock_init(self):
        """Test MockYubiKeyManager initialization."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = MockYubiKeyManager(config)

        assert yk.config == config
        assert yk.mock_present is True
        assert yk._ykman_available is True
        assert yk._yubikey_present is True

    def test_mock_is_available(self):
        """Test MockYubiKeyManager is_available."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = MockYubiKeyManager(config, mock_present=True)

        assert yk.is_available() is True

        # Test with mock_present=False
        yk2 = MockYubiKeyManager(config, mock_present=False)
        assert yk2.is_available() is False

        # Test with config disabled
        config._yubikey_enabled = False
        yk3 = MockYubiKeyManager(config, mock_present=True)
        assert yk3.is_available() is False

    def test_mock_encrypt_decrypt_workflow(self):
        """Test mock encryption and decryption workflow."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = MockYubiKeyManager(config)

        test_key = "AGE-SECRET-KEY-1TESTPRIVATEKEY1234567890"

        # Encrypt the key
        encrypted = yk.encrypt_age_key(test_key)
        assert encrypted.startswith(b"MOCK:")

        # Decrypt the key
        decrypted = yk.decrypt_age_key(encrypted)
        assert decrypted == test_key

        # Try to decrypt with wrong format
        with pytest.raises(YubiKeyError, match="Mock key not found"):
            yk.decrypt_age_key(b"WRONG:format")

    def test_mock_verify_pin(self):
        """Test mock PIN verification."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = MockYubiKeyManager(config)

        # Default mock PIN is "123456"
        assert yk.verify_pin("123456") is True
        assert yk.verify_pin("wrong") is False

    def test_mock_change_pin(self):
        """Test mock PIN change."""
        config = VaultConfig()
        config._yubikey_enabled = True
        yk = MockYubiKeyManager(config)

        # Old PIN must be "123456" and new PIN at least 6 chars
        assert yk.change_pin("123456", "654321") is True
        assert yk.change_pin("wrong", "654321") is False
        assert yk.change_pin("123456", "short") is False


def test_yubikey_error():
    """Test YubiKeyError exception."""
    error = YubiKeyError("Test error")
    assert str(error) == "Test error"

    # Test with custom message
    error2 = YubiKeyError("Encryption failed")
    assert str(error2) == "Encryption failed"


@pytest.mark.hardware
class TestYubiKeyIntegration:
    """Integration tests for YubiKey (requires actual YubiKey hardware)."""

    @pytest.mark.skip(reason="Requires physical YubiKey hardware")
    def test_real_yubikey_detection(self):
        """Test actual YubiKey detection (requires hardware)."""
        config = VaultConfig()
        config._yubikey_enabled = True
        _ = YubiKeyManager(config)

        # This test will only pass if ykman is installed and YubiKey is present
        # It's skipped by default
        pass
