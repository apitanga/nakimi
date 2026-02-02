#!/usr/bin/env python3
"""
Script to rename references in documentation files from Kimi to Nakimi.
"""

import os
import re
from pathlib import Path

# Mapping of patterns to replacements
REPLACEMENTS = [
    # Project name variations
    (r"Kimi Secrets Vault", "Nakimi"),
    (r"kimi-secrets-vault", "nakimi"),
    (r"kimi_vault", "nakimi"),
    # CLI command
    (r"kimi-vault", "nakimi"),
    # Directory paths
    (r"~/.kimi-vault", "~/.nakimi"),
    (r"~/.config/kimi-vault", "~/.config/nakimi"),
    # Environment variables
    (r"KIMI_VAULT_", "NAKIMI_"),
    # URLs (keep as is for now, will be updated after repo rename)
    # (r"github\.com/apitanga/kimi-secrets-vault", "github.com/apitanga/nakimi"),
    # Badge URLs (same)
]

# Files to process (markdown files)
def find_markdown_files(root_dir):
    md_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            if f.endswith('.md'):
                md_files.append(Path(dirpath) / f)
    return md_files

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    for pattern, replacement in REPLACEMENTS:
        # Use regex to replace whole words? We'll use simple regex
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        print(f"Updated {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    root_dir = Path(__file__).parent
    md_files = find_markdown_files(root_dir)
    
    updated = 0
    for md in md_files:
        if process_file(md):
            updated += 1
    
    print(f"Updated {updated} of {len(md_files)} markdown files.")

if __name__ == "__main__":
    main()