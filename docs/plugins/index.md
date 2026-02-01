---
title: Plugins
nav_order: 20
has_children: true
---

# Plugins

Kimi Secrets Vault uses a plugin-based architecture to integrate with various services. Each plugin provides credential management for a specific API or service.

## Available Plugins

- [Gmail Plugin](GMAIL_SETUP.md) - Google Gmail API integration
- More plugins coming soon...

## Plugin Development

Want to create your own plugin? Check out the [Plugin Development Guide](../development/PLUGIN_DEVELOPMENT.md) for detailed instructions.

## How Plugins Work

1. Plugins auto-discover available credentials in your vault
2. Each plugin provides specific commands for its service
3. Plugins run with the same security model as the main vault
4. Environment variables connect plugins to decrypted secrets