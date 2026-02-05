---
title: HOME
nav_order: 0
---

# Nakimi

Secure, plugin-based API credential management for AI assistants

## Overview
Nakimi is a secure, plugin-based API credential management system for AI assistants with age encryption. It provides encrypted storage for API credentials with just-in-time decryption, plugin-based service integration, and a simple CLI interface.

## Quick Links

- **[Getting Started](./getting-started/)** - Installation and setup guides
- **[Examples](./examples/)** - Practical examples and usage patterns
- **[Plugins](./plugins/)** - Plugin setup and configuration
- **[Development](./development/)** - Plugin development and architecture
- **[Security](./security/)** - Security architecture and policies
- **[API Reference](./api/)** - Python API and plugin development
- **[Project](./project/)** - Project reports and roadmap

## Core Features

### 🔐 Security First
- Age encryption for credential storage
- RAM-backed temporary files with `mlock()` support
- Secure deletion with `shred`
- YubiKey hardware encryption support (optional)
- Just-in-time decryption

### 🔌 Plugin-Based
- Auto-discovery based on available credentials
- Easy to extend with new services
- Standard plugin interface

### 🖥️ CLI Focused
- Simple `plugin.command` syntax
- Session mode for secure workflows
- Clear error messages with emoji indicators

## Project Status
**Current Version**: 2.0.0 (beta)  
**Test Coverage**: 56% (107 tests total)  
**Active Development**: Yes

## Getting Help
- [GitHub Issues](https://github.com/apitanga/nakimi/issues) - Report bugs or request features
- [Contributing Guide](../CONTRIBUTING.md) - How to contribute
- [Security Policy](security/SECURITY.md) - Security reporting and policies

---

*Documentation last updated: 2026-02-01*