#!/usr/bin/env python3
"""
Fast parallel SSH downloader - WITH PROGRESS DURING SCANNING
Shows what's happening while it scans the directory
"""

import os
import sys
import stat
import argparse
import paramiko
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging
from getpass import getpass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SSHFileDownloader:
    def __init__(self, hostname, username, port=22, password=None, key_file=None, 
                 num_workers=8):
        self.hostname = hostname
        self.username = username
        self.port = port
        self.password = password
        self.key_file = key_file
        self.num_workers = num_workers
        
    def _create_ssh_client(self):
        """Create and authenticate SSH client"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if self.key_file:
                client.connect(self.hostname, port=self.port, username=self.username,
                             key_filename=self.key_file, timeout=10)
                logger.info(f"Connected via key file: {self.key_file}")
            elif self.password:
                client.connect(self.hostname, port=self.port, username=self.username,
                             password=self.password, timeout=10)
                logger.info("Connected via password")
            else:
                client.connect(self.hostname, port=self.port, username=self.username,
                             timeout=10)
                logger.info("Connected via SSH key")
            return client
        except paramiko.AuthenticationException as e:
            logger.error(f"Authentication failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise
    
    def get_file_list(self, remote_path):
        """Recursively get list of files from remote server WITH PROGRESS"""
        client = self._create_ssh_client()
        sftp = client.open_sftp()
        
        files = []
        pbar = tqdm(desc="Scanning directories", unit=" dirs", leave=True)
        
        def walk(path):
            try:
                pbar.update(1)
                pbar.set_description(f"Scanning: {path}")
                
                items = sftp.listdir_attr(path)
                for item in items:
                    full_path = f"{path}/{item.filename}".replace('//', '/')
                    if stat.S_ISDIR(item.st_mode):
                        walk(full_path)
                    else:
                        rel_path = full_path.replace(remote_path, '').lstrip('/')
                        files.append({
                            'remote_path': full_path,
                            'relative_path': rel_path,
                            'size': item.st_size
                        })
            except PermissionError:
                logger.warning(f"Permission denied: {path}")
            except Exception as e:
                logger.warning(f"Error walking {path}: {e}")
        
        try:
            logger.info(f"Starting to scan files...")
            walk(remote_path)
            pbar.close()
            logger.info(f"✅ Found {len(files)} files total")
            return files
        finally:
            sftp.close()
            client.close()
    
    def download_file(self, file_info, output_dir):
        """Download single file via SFTP"""
        remote_path = file_info['remote_path']
        local_path = Path(output_dir) / file_info['relative_path']
        
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        client = None
        try:
            client = self._create_ssh_client()
            sftp = client.open_sftp()
            
            if local_path.exists():
                local_size = local_path.stat().st_size
                remote_size = sftp.stat(remote_path).st_size
                
                if local_size == remote_size:
                    return {'status': 'skip', 'file': file_info['relative_path']}
                elif local_size < remote_size:
                    logger.info(f"Resuming {file_info['relative_path']} from {local_size} bytes")
            
            remote_size = sftp.stat(remote_path).st_size
            
            with open(local_path, 'wb') as f:
                with tqdm(total=remote_size, unit='B', unit_scale=True,
                         desc=file_info['relative_path'], leave=False) as pbar:
                    sftp.getfo(remote_path, f, callback=lambda t, s: pbar.update(t))
            
            return {'status': 'success', 'file': file_info['relative_path']}
        
        except Exception as e:
            return {'status': 'error', 'file': file_info['relative_path'], 'error': str(e)}
        
        finally:
            if client:
                try:
                    sftp.close()
                except:
                    pass
                client.close()
    
    def download_all(self, file_list, output_dir):
        """Download all files in parallel"""
        logger.info(f"Starting download of {len(file_list)} files with {self.num_workers} workers...")
        
        results = {'success': 0, 'skip': 0, 'error': 0, 'errors': []}
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self.download_file, f, output_dir): f 
                      for f in file_list}
            
            with tqdm(total=len(file_list), desc="Download Progress") as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    
                    if result['status'] == 'success':
                        results['success'] += 1
                    elif result['status'] == 'skip':
                        results['skip'] += 1
                    else:
                        results['error'] += 1
                        results['errors'].append(result)
                    
                    pbar.update(1)
        
        return results

def main():
    parser = argparse.ArgumentParser(
        description='Fast parallel SSH/SFTP image downloader'
    )
    parser.add_argument('--host', required=True, help='Remote host')
    parser.add_argument('--user', required=True, help='SSH username')
    parser.add_argument('--path', required=True, help='Remote path to download from')
    parser.add_argument('--output', required=True, help='Local output directory')
    parser.add_argument('--port', type=int, default=22, help='SSH port (default: 22)')
    parser.add_argument('--key', help='SSH private key file (optional)')
    parser.add_argument('--password', help='SSH password (optional, will prompt if not provided)')
    parser.add_argument('--workers', type=int, default=8, help='Parallel workers (default: 8)')
    
    args = parser.parse_args()
    
    password = args.password
    if not password and not args.key:
        password = getpass(f"Password for {args.user}@{args.host}: ")
    
    downloader = SSHFileDownloader(
        hostname=args.host,
        username=args.user,
        port=args.port,
        password=password,
        key_file=args.key,
        num_workers=args.workers
    )
    
    try:
        logger.info(f"Connecting to {args.host}...")
        file_list = downloader.get_file_list(args.path)
        
        if not file_list:
            logger.error("No files found")
            sys.exit(1)
        
        results = downloader.download_all(file_list, args.output)
        
        logger.info("\n" + "="*60)
        logger.info(f"✅ Download COMPLETE!")
        logger.info(f"  ✅ Succeeded: {results['success']}")
        logger.info(f"  ⏭️  Skipped:   {results['skip']}")
        logger.info(f"  ❌ Failed:    {results['error']}")
        logger.info("="*60)
        
        if results['errors']:
            logger.error("\n⚠️  Failed downloads:")
            for err in results['errors']:
                logger.error(f"  {err['file']}: {err['error']}")
    
    except KeyboardInterrupt:
        logger.info("\n⚠️  Download cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()