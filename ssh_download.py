#!/usr/bin/env python3
"""Parallel recursive downloader using SSH/SFTP."""

import argparse
import logging
import os
import posixpath
import stat
import sys
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from getpass import getpass
from pathlib import Path

import paramiko
from tqdm import tqdm


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class _ThreadLocalSFTP:
    """Keep one SSH/SFTP connection per executor thread."""

    def __init__(self, downloader):
        self.downloader = downloader
        self.local = threading.local()
        self.resources = []
        self.lock = threading.Lock()

    def get(self):
        resource = getattr(self.local, "resource", None)
        if resource is None:
            client = self.downloader._create_ssh_client()
            try:
                sftp = client.open_sftp()
                sftp.get_channel().settimeout(30)
            except Exception:
                client.close()
                raise

            resource = (client, sftp)
            self.local.resource = resource
            with self.lock:
                self.resources.append(resource)

        return resource[1]

    def close_current(self):
        resource = getattr(self.local, "resource", None)
        if resource is not None:
            self._close(resource)
            del self.local.resource

    def close_all(self):
        with self.lock:
            resources = list(self.resources)
            self.resources.clear()
        for resource in resources:
            self._close(resource)

    @staticmethod
    def _close(resource):
        client, sftp = resource
        try:
            sftp.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass


class SSHFileDownloader:
    def __init__(
        self,
        hostname,
        username,
        port=22,
        password=None,
        key_file=None,
        num_workers=8,
        scan_workers=4,
    ):
        self.hostname = hostname
        self.username = username
        self.port = port
        self.password = password
        self.key_file = key_file
        self.num_workers = max(1, num_workers)
        self.scan_workers = max(1, min(scan_workers, self.num_workers))

    def _create_ssh_client(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_options = {
            "hostname": self.hostname,
            "port": self.port,
            "username": self.username,
            "timeout": 10,
            "banner_timeout": 10,
            "auth_timeout": 10,
        }
        if self.key_file:
            connect_options["key_filename"] = self.key_file
        elif self.password:
            connect_options["password"] = self.password

        try:
            client.connect(**connect_options)
            return client
        except paramiko.AuthenticationException as exc:
            client.close()
            logger.error("Authentication failed: %s", exc)
            raise
        except Exception as exc:
            client.close()
            logger.error("Connection failed: %s", exc)
            raise

    @staticmethod
    def _scan_directory(sftp_pool, remote_path, root_path):
        try:
            directories = []
            files = []
            for item in sftp_pool.get().listdir_attr(remote_path):
                full_path = posixpath.join(remote_path, item.filename)
                if stat.S_ISDIR(item.st_mode):
                    directories.append(full_path)
                elif stat.S_ISREG(item.st_mode):
                    files.append(
                        {
                            "remote_path": full_path,
                            "relative_path": posixpath.relpath(full_path, root_path),
                            "size": item.st_size,
                        }
                    )
            return directories, files, None
        except Exception as exc:
            sftp_pool.close_current()
            return [], [], exc

    def get_file_list(self, remote_path):
        """Scan remote directories concurrently and return regular files."""
        root_path = posixpath.normpath(remote_path)
        sftp_pool = _ThreadLocalSFTP(self)
        executor = ThreadPoolExecutor(
            max_workers=self.scan_workers,
            thread_name_prefix="sftp-scan",
        )
        progress = tqdm(desc="Scanning directories", unit=" dirs")
        files = []
        pending = {
            executor.submit(
                self._scan_directory,
                sftp_pool,
                root_path,
                root_path,
            )
        }

        logger.info(
            "Scanning %s with %d parallel connection(s)...",
            root_path,
            self.scan_workers,
        )

        try:
            while pending:
                completed, pending = wait(
                    pending,
                    return_when=FIRST_COMPLETED,
                )
                for future in completed:
                    directories, discovered_files, error = future.result()
                    if error is not None:
                        logger.warning("Directory scan failed: %s", error)
                    files.extend(discovered_files)
                    for directory in directories:
                        pending.add(
                            executor.submit(
                                self._scan_directory,
                                sftp_pool,
                                directory,
                                root_path,
                            )
                        )
                    progress.update(1)
                    progress.set_postfix(files=len(files), refresh=False)
        except BaseException:
            for future in pending:
                future.cancel()
            sftp_pool.close_all()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
        finally:
            progress.close()
            sftp_pool.close_all()

        logger.info("Found %d files", len(files))
        return files

    @staticmethod
    def _download_file(sftp_pool, file_info, output_dir):
        remote_path = file_info["remote_path"]
        relative_path = file_info["relative_path"]
        remote_size = file_info["size"]
        local_path = Path(output_dir) / relative_path
        partial_path = local_path.with_name(f"{local_path.name}.part")

        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)

            if local_path.exists() and local_path.stat().st_size == remote_size:
                return {"status": "skip", "file": relative_path}

            offset = 0
            if partial_path.exists():
                partial_size = partial_path.stat().st_size
                if partial_size < remote_size:
                    offset = partial_size
                elif partial_size == remote_size:
                    os.replace(partial_path, local_path)
                    return {"status": "success", "file": relative_path}

            mode = "ab" if offset else "wb"
            sftp = sftp_pool.get()
            with sftp.open(remote_path, "rb") as remote_file:
                if offset:
                    remote_file.seek(offset)
                remote_file.prefetch(
                    file_size=remote_size,
                    max_concurrent_requests=64,
                )
                with open(partial_path, mode) as local_file:
                    while True:
                        chunk = remote_file.read(1024 * 1024)
                        if not chunk:
                            break
                        local_file.write(chunk)

            if partial_path.stat().st_size != remote_size:
                raise OSError(
                    f"size mismatch: expected {remote_size} bytes, "
                    f"received {partial_path.stat().st_size} bytes"
                )

            os.replace(partial_path, local_path)
            return {"status": "success", "file": relative_path}
        except Exception as exc:
            sftp_pool.close_current()
            return {
                "status": "error",
                "file": relative_path,
                "error": str(exc),
            }

    def download_all(self, file_list, output_dir):
        """Download with reusable connections and a bounded future queue."""
        results = {"success": 0, "skip": 0, "error": 0, "errors": []}
        sftp_pool = _ThreadLocalSFTP(self)
        executor = ThreadPoolExecutor(
            max_workers=self.num_workers,
            thread_name_prefix="sftp-download",
        )
        file_iterator = iter(file_list)
        pending = set()
        max_pending = self.num_workers * 2

        def submit_next():
            try:
                file_info = next(file_iterator)
            except StopIteration:
                return False
            pending.add(
                executor.submit(
                    self._download_file,
                    sftp_pool,
                    file_info,
                    output_dir,
                )
            )
            return True

        for _ in range(min(max_pending, len(file_list))):
            submit_next()

        logger.info(
            "Downloading %d files with %d reusable connection(s)...",
            len(file_list),
            self.num_workers,
        )

        progress = tqdm(total=len(file_list), desc="Downloading", unit=" files")
        try:
            while pending:
                completed, still_pending = wait(
                    pending,
                    return_when=FIRST_COMPLETED,
                )
                pending = set(still_pending)

                for future in completed:
                    result = future.result()
                    status = result["status"]
                    results[status] += 1
                    if status == "error":
                        results["errors"].append(result)
                    progress.update(1)

                for _ in range(len(completed)):
                    submit_next()

                progress.set_postfix(
                    ok=results["success"],
                    skipped=results["skip"],
                    failed=results["error"],
                    refresh=False,
                )
        except BaseException:
            for future in pending:
                future.cancel()
            sftp_pool.close_all()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
        finally:
            progress.close()
            sftp_pool.close_all()

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Fast parallel SSH/SFTP downloader"
    )
    parser.add_argument("--host", required=True, help="Remote host")
    parser.add_argument("--user", required=True, help="SSH username")
    parser.add_argument("--path", required=True, help="Remote directory")
    parser.add_argument("--output", required=True, help="Local output directory")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--key", help="SSH private key file")
    parser.add_argument(
        "--password",
        nargs="?",
        const=True,
        help="Prompt for a password, or provide it as the argument value",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel download connections (default: 8)",
    )
    parser.add_argument(
        "--scan-workers",
        type=int,
        default=4,
        help="Parallel scan connections (default: 4)",
    )
    args = parser.parse_args()

    password = args.password
    if password is True or (not password and not args.key):
        password = getpass(f"Password for {args.user}@{args.host}: ")

    downloader = SSHFileDownloader(
        hostname=args.host,
        username=args.user,
        port=args.port,
        password=password,
        key_file=args.key,
        num_workers=args.workers,
        scan_workers=args.scan_workers,
    )

    try:
        file_list = downloader.get_file_list(args.path)
        if not file_list:
            logger.error("No files found")
            return 1

        results = downloader.download_all(file_list, args.output)
        logger.info(
            "Download complete: %d succeeded, %d skipped, %d failed",
            results["success"],
            results["skip"],
            results["error"],
        )

        if results["errors"]:
            logger.error("Failed downloads:")
            for error in results["errors"]:
                logger.error("  %s: %s", error["file"], error["error"])
            return 1
        return 0
    except KeyboardInterrupt:
        logger.info("Download cancelled by user")
        return 130
    except Exception as exc:
        logger.error("Error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
