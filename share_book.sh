#!/bin/bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: $0 BOOK_URL BUCKET EXPIRES_SECONDS" >&2
  exit 1
fi

BOOK_URL="$1"
BUCKET="$2"
EXPIRES_SECONDS="$3"
FILENAME="${BOOK_URL##*/}"

if [[ ! "$EXPIRES_SECONDS" =~ ^[0-9]+$ ]] || (( EXPIRES_SECONDS < 1 || EXPIRES_SECONDS > 604800 )); then
  echo "EXPIRES_SECONDS must be between 1 and 604800." >&2
  exit 1
fi

# Download the book.
mkdir -p books
curl -fL --retry 3 --retry-all-errors --retry-delay 1 --max-time 30 "$BOOK_URL" -o "books/$FILENAME"

# Create a private bucket if needed.
if ! aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
  aws s3 mb "s3://$BUCKET"
fi

# Upload the book.
aws s3 cp "books/$FILENAME" "s3://$BUCKET/$FILENAME" --content-type "text/plain; charset=utf-8"

# Print a temporary download URL.
aws s3 presign "s3://$BUCKET/$FILENAME" --expires-in "$EXPIRES_SECONDS" --region us-east-1
