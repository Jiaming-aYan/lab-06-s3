#!/usr/bin/env python3
"""Stage Gutenberg books in a public S3 bucket."""

import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import boto3
import requests
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    """Return the book list, index page, and bucket name."""
    if len(sys.argv) != 4:
        log.error("Usage: stage_books.py BOOK_URLS INDEX_HTML BUCKET")
        sys.exit(1)
    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download books and return their local paths."""
    try:
        os.makedirs(dest_dir, exist_ok=True)
        with open(list_file, encoding="utf-8") as source:
            urls = [line.strip() for line in source if line.strip()]
    except OSError as exc:
        log.error("Cannot read book list: %s", exc)
        return []

    paths = []
    for url in urls:
        filename = os.path.basename(urlparse(url).path)
        if not filename:
            log.error("Invalid book URL: %s", url)
            continue

        path = os.path.join(dest_dir, filename)
        if os.path.exists(path):
            paths.append(path)
            continue

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            with open(path, "wb") as output:
                output.write(response.content)
        except (requests.RequestException, OSError) as exc:
            log.error("Download failed for %s: %s", url, exc)
        else:
            paths.append(path)
            log.info("Downloaded %s", filename)
        time.sleep(1)

    return paths


def create_bucket(bucket):
    """Create the bucket if it does not exist."""
    try:
        s3.head_bucket(Bucket=bucket)
        log.info("Bucket exists: %s", bucket)
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            log.error("Cannot check bucket %s: %s", bucket, exc)
            return False

    try:
        s3.create_bucket(Bucket=bucket)
        log.info("Created bucket: %s", bucket)
        return True
    except ClientError as exc:
        log.error("Cannot create bucket %s: %s", bucket, exc)
        return False


def make_public(bucket):
    """Allow public read access to bucket objects."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/*",
            }
        ],
    }
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        log.info("Public read enabled: %s", bucket)
        return True
    except ClientError as exc:
        log.error("Cannot make bucket public: %s", exc)
        return False


def upload_files(bucket, file_paths):
    """Upload text files and return the successful count."""
    uploaded = 0
    for path in file_paths:
        key = os.path.basename(path)
        try:
            with open(path, "rb") as source:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=source,
                    ContentType="text/plain; charset=utf-8",
                )
            uploaded += 1
        except (OSError, ClientError) as exc:
            log.error("Cannot upload %s: %s", path, exc)
    log.info("Uploaded books: %d/%d", uploaded, len(file_paths))
    return uploaded


def upload_index(bucket, index_path):
    """Upload the index page."""
    try:
        with open(index_path, "rb") as source:
            s3.put_object(
                Bucket=bucket,
                Key="index.html",
                Body=source,
                ContentType="text/html",
            )
        log.info("Uploaded index.html")
        return True
    except (OSError, ClientError) as exc:
        log.error("Cannot upload %s: %s", index_path, exc)
        return False


def main():
    """Stage the books and index page in S3."""
    list_file, index_path, bucket = parse_args()
    paths = download_books(list_file, "books")
    if not paths:
        log.error("No books available")
        sys.exit(1)
    if not create_bucket(bucket) or not make_public(bucket):
        sys.exit(1)
    uploaded = upload_files(bucket, paths)
    index_uploaded = upload_index(bucket, index_path)
    if uploaded != len(paths) or not index_uploaded:
        log.error("Staging incomplete")
        sys.exit(1)
    log.info("https://%s.s3.amazonaws.com/index.html", bucket)


if __name__ == "__main__":
    main()
