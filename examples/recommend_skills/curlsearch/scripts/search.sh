#!/bin/bash
# curl-search: Web search using curl + multiple search engines
# Security: Input sanitization and command injection protection enabled

# Default settings
SEARCH_ENGINE="${SEARCH_ENGINE:-baidu}"
MAX_RESULTS="${MAX_RESULTS:-10}"

# Security: Validate and sanitize input
sanitize_input() {
    local input="$1"
    # Remove any shell metacharacters that could be exploited
    echo "$input" | sed 's/[^a-zA-Z0-9 \_\-\.\~\x{4e00}-\x{9fff}]//g'
}

# Security: URL encode with proper escaping
encode_url() {
    local input="$1"
    python3 -c "import urllib.parse; print(urllib.parse.quote('$input', safe=''))"
}

# Help information
show_help() {
    echo "Usage: search.sh [OPTIONS] <search query>"
    echo ""
    echo "Options:"
    echo "  -e, --engine    Search engine: baidu, google, bing, duckduckgo (default: baidu)"
    echo "  -n, --results   Number of results (default: 10)"
    echo "  -h, --help      Show this help"
    echo ""
    echo "Examples:"
    echo "  search.sh OpenClaw tutorial"
    echo "  search.sh -e google -n 5 AI development"
    echo "  SEARCH_ENGINE=google search.sh machine learning"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--engine)
            SEARCH_ENGINE="$2"
            shift 2
            ;;
        -n|--results)
            MAX_RESULTS="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

# Security: Validate search engine
case "$SEARCH_ENGINE" in
    baidu|bd|google|g|bing|b|duckduckgo|ddg)
        # Valid engine
        ;;
    *)
        echo "Error: Invalid search engine: $SEARCH_ENGINE"
        echo "Supported: baidu, google, bing, duckduckgo"
        exit 1
        ;;
esac

# Security: Validate max results is numeric
if ! [[ "$MAX_RESULTS" =~ ^[0-9]+$ ]] || [ "$MAX_RESULTS" -lt 1 ] || [ "$MAX_RESULTS" -gt 50 ]; then
    echo "Error: Invalid max results (must be 1-50)"
    exit 1
fi

# Get remaining args as query
query="$*"
if [ -z "$query" ]; then
    show_help
    exit 1
fi

# Security: Sanitize user input before use
query=$(sanitize_input "$query")

# Security: Check for empty after sanitization
if [ -z "$query" ]; then
    echo "Error: Invalid input after sanitization"
    exit 1
fi

# URL encode the sanitized query
query=$(encode_url "$query")

# Baidu search
search_baidu() {
    local url="http://www.baidu.com/s?wd=${query}"
    curl -s -L "$url" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" 2>/dev/null | \
        sed 's/<[^>]*>//g' | \
        sed 's/[[:space:]]\+/ /g' | \
        grep -iE "官网|文档|教程|安装|部署|配置|使用|免费|download|github|docs|guide|install|setup|tutorial" | \
        head -"$MAX_RESULTS"
}

# Google search
search_google() {
    local url="https://www.google.com/search?q=${query}"
    curl -s -L "$url" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" 2>/dev/null | \
        sed 's/<[^>]*>//g' | \
        sed 's/[[:space:]]\+/ /g' | \
        head -"$MAX_RESULTS"
}

# Bing search
search_bing() {
    local url="https://www.bing.com/search?q=${query}"
    curl -s -L "$url" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" 2>/dev/null | \
        sed 's/<[^>]*>//g' | \
        sed 's/[[:space:]]\+/ /g' | \
        head -"$MAX_RESULTS"
}

# DuckDuckGo search
search_duckduckgo() {
    local url="https://duckduckgo.com/?q=${query}"
    curl -s -L "$url" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" 2>/dev/null | \
        sed 's/<[^>]*>//g' | \
        sed 's/[[:space:]]\+/ /g' | \
        grep -iE "github|doc|wiki|tutorial" | \
        head -"$MAX_RESULTS"
}

# Main function
main() {
    echo "🔍 Search"
    echo "🌐 Engine: $SEARCH_ENGINE"
    echo "---"
    
    case "$SEARCH_ENGINE" in
        baidu|bd)
            search_baidu
            ;;
        google|g)
            search_google
            ;;
        bing|b)
            search_bing
            ;;
        duckduckgo|ddg)
            search_duckduckgo
            ;;
    esac
}

main
