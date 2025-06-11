#!/usr/bin/env python3
"""
Cleanup script for the sales-ai-1 project.
This script removes temporary files, compiled Python files, and manages large files in uploads directory.
"""

import os
import shutil
import subprocess
import argparse
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cleanup")

def remove_pycache_files():
    """Remove all __pycache__ directories and .pyc files."""
    count = 0
    
    # Remove __pycache__ directories
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            try:
                shutil.rmtree(pycache_path)
                count += 1
                logger.info(f"Removed: {pycache_path}")
            except Exception as e:
                logger.error(f"Failed to remove {pycache_path}: {e}")
    
    # Remove .pyc files
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.pyc'):
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    count += 1
                    logger.info(f"Removed: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to remove {file_path}: {e}")
    
    return count

def remove_temp_files():
    """Remove temporary, backup, and system files."""
    patterns = [
        "*.bak", "*.tmp", "*.swp", "*.swo", 
        ".DS_Store", "._*", "~*", "Thumbs.db",
        "*.log", "*.orig"
    ]
    
    count = 0
    for pattern in patterns:
        cmd = ["find", ".", "-type", "f", "-name", pattern]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            files = result.stdout.strip().split("\n")
            for file in files:
                if file and os.path.exists(file):
                    os.remove(file)
                    count += 1
                    logger.info(f"Removed: {file}")
        except Exception as e:
            logger.error(f"Error finding {pattern} files: {e}")
    
    return count

def cleanup_duplicate_files():
    """Remove duplicate files like index.html.new, etc."""
    duplicates = [
        "templates/index.html.new",
        "templates/index.html.fixed"
    ]
    
    count = 0
    for file_path in duplicates:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                count += 1
                logger.info(f"Removed duplicate file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to remove {file_path}: {e}")
    
    return count

def clean_uploads_directory():
    """
    Clean all files in the uploads directory since we no longer need to store uploaded files.
    """
    if not os.path.exists("uploads"):
        logger.warning("Uploads directory not found")
        return 0
    
    # Get all files in uploads directory
    upload_files = []
    for file in os.listdir("uploads"):
        file_path = os.path.join("uploads", file)
        if os.path.isfile(file_path):
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            upload_files.append((file_path, size_mb))
    
    removed_count = 0
    saved_space = 0
    
    # Remove all files (keeping directory structure)
    for file_path, size_mb in upload_files:
        try:
            os.remove(file_path)
            removed_count += 1
            saved_space += size_mb
            logger.info(f"Removed {file_path} ({size_mb:.2f} MB)")
        except Exception as e:
            logger.error(f"Failed to remove {file_path}: {e}")
    
    if removed_count > 0:
        logger.info(f"Freed up {saved_space:.2f} MB by removing {removed_count} files from uploads directory")
    
    return removed_count

def main():
    parser = argparse.ArgumentParser(description="Cleanup script for sales-ai-1 project")
    parser.add_argument("--all", action="store_true", help="Run all cleanup operations")
    parser.add_argument("--pycache", action="store_true", help="Remove __pycache__ directories and .pyc files")
    parser.add_argument("--temp", action="store_true", help="Remove temporary files")
    parser.add_argument("--duplicates", action="store_true", help="Remove duplicate files")
    parser.add_argument("--uploads", action="store_true", help="Clean all files in uploads directory")
    
    args = parser.parse_args()
    
    # If no specific option is selected, show help
    if not (args.all or args.pycache or args.temp or args.duplicates or args.uploads):
        parser.print_help()
        return
    
    # Run selected cleanup operations
    total_count = 0
    
    if args.all or args.pycache:
        count = remove_pycache_files()
        logger.info(f"Removed {count} Python cache files and directories")
        total_count += count
    
    if args.all or args.temp:
        count = remove_temp_files()
        logger.info(f"Removed {count} temporary and system files")
        total_count += count
    
    if args.all or args.duplicates:
        count = cleanup_duplicate_files()
        logger.info(f"Removed {count} duplicate files")
        total_count += count
    
    if args.all or args.uploads:
        count = clean_uploads_directory()
        if count > 0:
            logger.info(f"Cleaned {count} files from uploads directory")
        total_count += count
    
    logger.info(f"Cleanup complete - removed {total_count} files/directories in total")

if __name__ == "__main__":
    main() 