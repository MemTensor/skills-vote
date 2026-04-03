---
name: curl-search
description: "Web search using curl + multiple search engines (Baidu, Google, Bing, DuckDuckGo). Activates when user asks to search, look up, or query something online. Includes security enhancements: input sanitization, command injection protection, and URL encoding."
metadata:
  requirements:
    binaries:
      - curl
      - python3
    os:
      - linux
      - darwin
      - win32
  security:
    input_sanitization: true
    command_injection_protection: true
    url_encoding: true
  version: "2.0.0"
  author: "bluejoy34"
  license: "MIT"
---

# Curl Search Skill

Web search using curl + multiple search engines. This skill provides a lightweight alternative when dedicated search APIs are unavailable.

## Supported Search Engines

| Engine | Alias | Description |
|--------|-------|-------------|
| Baidu | bd | Fast for China, default option |
| Google | g | Requires proxy/VPN in China |
| Bing | b | Microsoft Bing |
| DuckDuckGo | ddg | Privacy-focused search |

## Usage Examples

```
Search for OpenClaw tutorial
Google search AI development
Find Python tutorials with bing
```

## Requirements

- **curl** - Command-line HTTP client
- **python3** - For URL encoding

## Security Features

This skill includes several security enhancements:

### 1. Input Sanitization
Removes dangerous shell metacharacters that could be exploited:
```bash
sanitize_input() {
    local input="$1"
    echo "$input" | sed 's/[^a-zA-Z0-9 \_\-\.\~\x{4e00}-\x{9fff}]//g'
}
```

### 2. Command Injection Protection
- Validates search engine selection
- Restricts max results to 1-50
- Checks for empty input after sanitization

### 3. URL Encoding
Uses Python's urllib.parse with safe='' parameter to properly encode special characters.

## Installation

```bash
# Install via ClawHub
clawhub install curl-search

# Or manually
cd your-skills-dir
tar -xzf curl-search.tar.gz
```

## Configuration

Set default search engine:
```bash
export SEARCH_ENGINE=google
```

Set max results:
```bash
export MAX_RESULTS=5
```

## Limitations

- Search results come from public search engines
- May be blocked by anti-scraping measures
- Google requires proxy/VPN in China

## Version History

- **2.0.0** - Security enhancements added
  - Input sanitization
  - Command injection protection
  - URL encoding improvements
- **1.0.0** - Initial release
