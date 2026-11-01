#!/usr/bin/env bash
# Remove AI attribution trailers so Vijay is the sole author.
sed -i.bak -E '/^(Co-[Aa]uthored-[Bb]y:.*|Claude-Session:.*|.*Generated with \[?(Claude|Codex).*)$/d' "$1"
rm -f "$1.bak"
