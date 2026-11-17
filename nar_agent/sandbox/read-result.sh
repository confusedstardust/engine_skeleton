#!/bin/sh
# Fixed tmpfs reader. Do not start V8/thread pools while Chromium is running.
case "${1-}" in
  report.json) limit=128000 ;;
  index.html) limit=2000000 ;;
  preview.png|mobile.png) limit=3000000 ;;
  *) echo 'Unexpected result filename' >&2; exit 4 ;;
esac
file="/results/$1"
[ -e "$file" ] || exit 3
if [ ! -f "$file" ] || [ -L "$file" ]; then
  echo 'Result must be a regular file, not a symlink' >&2
  exit 4
fi
size=$(LC_ALL=C wc -c < "$file") || exit 4
if [ "$size" -gt "$limit" ]; then
  echo 'Result exceeds size limit' >&2
  exit 4
fi
exec cat -- "$file"
