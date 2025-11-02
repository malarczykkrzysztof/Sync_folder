#!/usr/bin/env python3

import sys
import os
import shutil
import time
import hashlib
import logging.config
from typing import Dict, Tuple
from pathlib import Path
from functools import partial
from dataclasses import dataclass

logging_config = {
    "version": 1,
    "formatters": {
        "simple": { 
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S%z"
        }
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "simple",
            "filename": "Fsync.log",
            "mode": "a",
            "maxBytes": 1000000,
            "backupCount": 3 
        }
    },
    "loggers": {
        "Fsync": {
            "handlers": ["stdout", "file"],
            "level": "INFO"
        }
    }
}

@dataclass
class FileDescription:
  path: Path
  exists: bool | None = None
  is_symlink: bool | None = None 
  is_file: bool | None = None  
  is_dir: bool | None = None  
  is_readable: bool | None = None  
  is_writable: bool | None = None  


def copy_file_with_attributes(src: str, dst: str, logger: logging.Logger):
    try:
        if os.path.islink(src):
            if os.path.exists(dst):
                os.remove(dst)
            link_target = os.readlink(src)
            os.symlink(link_target, dst)
            logger.info(f"SYMLINK     : {dst} -> {link_target}")
            return

        shutil.copy2(src, dst)
        shutil.copymode(src, dst)
        st = os.stat(src, follow_symlinks=False)
        try:
            os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)
        except PermissionError:
            logger.warning(f"Cannot change owner/group for {dst}, running without root privileges")
    except Exception as e:
        logger.error(f"ERROR COPY FILE: {src} -> {dst}: {e}")

class Parser:
    
    def __init__(self, argv: list):
        self.is_correct_num_of_arguments(argv)
        _, source, replica, interval, iterations, log = argv
        
        try:
            self.source = FileDescription(path = self.convert_to_path(source))
            self.replica = FileDescription(path = self.convert_to_path(replica))
            self.log = FileDescription(path = self.convert_to_path(log))   
            self.interval = float(interval)
            self.iterations = int(iterations)       
        except Exception as e:
            raise ValueError(f"Incorrect argument: {e}")
   
    @staticmethod
    def convert_to_path(file_path: str) -> Path:
        if isinstance(file_path, Path):
            return file_path.resolve(strict=False)
        else:
            return Path(file_path).resolve(strict=False)

    @staticmethod    
    def is_correct_num_of_arguments(argv: list) -> None:
        if len(argv) != 6:
            raise ValueError(
                "Accepted input arguments: 'path to source folder' 'path to replica folder' "
                "<interval between synchronizations> <amount of synchronizations> "
                "'path to log file'"
            )   
    
    def run(self) -> list[Path|float|int]:
        self._check_interval()
        self._check_amount_of_synchronizations()       
        self._check_files()
        return [self.source.path, self.replica.path, self.log.path, self.interval, self.iterations]   
    
    def _check_interval(self) -> None:
        if self.interval < 0:
            raise ValueError("Error: interval must be non-negative float.") 
    
    def _check_amount_of_synchronizations(self) -> None:
        if self.iterations <= 0:
            raise ValueError("Error: amount of synchronizations must be positive integer.")
        
    def _check_files(self) -> None:
        self._check_source_path()
        self._prepare_path_for_writing(self.replica, dir = True)
        self._prepare_path_for_writing(self.log, dir = False)
        self._check_paths_dependency()    
        
    def _check_source_path(self)  -> None: 
        self.source.exists=True
        self.source.is_dir=True
        self.source.is_readable=True
        self._check_and_update_attributes(self.source)
        self._raise_error_for_incorrect_attribute(self.source)
       
    def _check_and_update_attributes(self, file: FileDescription) -> None:
        if file.exists: 
            file.exists = file.path.exists()
        if file.is_symlink:
            file.is_symlink = file.path.is_symlink()
        if file.is_file:
            file.is_file = file.path.is_file()
        if file.is_dir:
            file.is_dir = file.path.is_dir()
        if file.is_writable:
            file.is_writable = os.access(str(file.path), os.W_OK)
        if file.is_readable:
            file.is_readable = os.access(str(file.path), os.R_OK)
               
    def _raise_error_for_incorrect_attribute( self, file: FileDescription) -> None:   
        if file.exists == False: 
            raise FileNotFoundError(f"File does not exist: {file.path}")
        if file.is_symlink == False:
            raise ValueError(f"File is not symbolic link: {file.path}")
        if file.is_dir == False: 
            raise ValueError(f"File is not a directory: {file.path}")
        if file.is_readable == False: 
            raise PermissionError(f"File is not readable: {file.path}")  
        if file.is_writable == False: 
            raise PermissionError(f"File is not writable: {file.path}")
        if file.is_file == False: 
            raise ValueError(f"File name is not a file: {file.path}")
        
    def _prepare_path_for_writing(self, file: FileDescription, dir:bool) -> None:
        print(f"Preparing {'directory' if dir else 'file'}: {file.path}")

        file.exists = True
        file.is_readable = True
        file.is_writable = True
        if dir:
            file.is_dir = True
        else:
            file.is_file = True
       
        self._check_and_update_attributes(file)
        if file.exists:
            self._raise_error_for_incorrect_attribute(file)
            print(f"{'Directory' if dir else 'File'} {file.path} already exists and is valid.")

        else:
            self._create_final_destination_path(file, dir)
 
    def _create_final_destination_path(self, file: FileDescription, dir:bool) -> None: 
            parent = FileDescription(path = file.path.parent,
                                     exists = True,
                                     is_dir = True,
                                     is_readable = True,
                                     is_writable = True)
            
            self._check_and_update_attributes(parent)
            self._raise_error_for_incorrect_attribute(parent)

            try:
                if dir:
                    file.path.mkdir(parents=True)
                    print(f"CREATE_DIR  : {file.path}")
                else:
                    file.path.touch(exist_ok=True)
                    print(f"CREATE_FILE : {file.path}")
            except Exception as e:
                raise OSError(f"ERROR CREATE {'DIR' if dir else 'FILE'}: {parent.path}: {e}")  
    
    def _check_paths_dependency (self) -> None:
        if self.log.path.is_relative_to(self.source.path):
            raise ValueError("Log file path cannot be inside source directory.")
        
        if self.log.path.is_relative_to(self.replica.path):   
            raise ValueError("Log file path cannot be inside replica directory.")
        
        if self.source.path.is_relative_to(self.replica.path):
            raise ValueError("Source path cannot be inside replica directory.")
            
        if self.replica.path.is_relative_to(self.source.path):   
            raise ValueError("Replica path cannot be inside source directory.")

class FolderSync:
 
    def __init__(self, 
                 source: Path,
                 replica: Path,
                 log: Path, 
                 interval: float, 
                 iterations: int):
        self.source = source
        self.replica = replica
        self.interval = interval
        self.iterations = iterations
        self.log_path = log
        self.logger = self._setup_logging() 
    
    
    def _setup_logging(self) -> logging.Logger:
        logging_config["handlers"]["file"]["filename"] = self.log_path
        logging.config.dictConfig(logging_config)
        return logging.getLogger("Fsync")
    
    def run(self) -> None:
        self._init_log()
        self.compute_first_file_hash(self.source)

        executed = 0
        start_total = time.time()
        next_run = start_total
        while executed < self.iterations and (time.time() - start_total) < self.interval * self.iterations:
            now = time.time()
            if now < next_run:
                time.sleep(next_run - now)

            executed += 1
            self.logger.info(f"--- Sync {executed}/{self.iterations} START ---")
            next_run += self.interval
            if self.skip_if_not_enough_space():
                continue
            if self.skip_if_source_and_replica_identical():
                continue

            start_sync = time.time()
            try:
                self.sync_files()
            except Exception as e:
                self.logger.error(f"SYNC ERROR: {e}")
            elapsed_sync = time.time() - start_sync
            self.logger.info(f"--- Sync {executed}/{self.iterations} END (elapsed {elapsed_sync:.2f}s) ---")

        self.logger.info(f"END SYNC (executed {executed} synchronizations in {time.time()-start_total:.2f}s)")    
    
    def skip_if_source_and_replica_identical(self):
        source_hash = self.compute_folder_hash(self.source)
        replica_hash = self.compute_folder_hash(self.replica)
        if source_hash == replica_hash:
                self.logger.info("Source and replica are identical — skipping this synchronization.")
                return True
    
    def _init_log(self):
        self.logger.info("START SYNC")
        self.logger.info(f"Source: {self.source}")
        self.logger.info(f"Replica: {self.replica}")
        self.logger.info(f"Interval: {self.interval}s")
        self.logger.info(f"Max iterations: {self.iterations}")
        self.logger.info(f"Log file: {self.log_path}")
    
    def compute_first_file_hash(self, folder_path: Path):
        for file_path in folder_path.rglob("*"):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            try:
                result =  self.compute_file_md5(str(file_path))
            except (OSError, IOError) as e:
                self.logger.warning(f"Failed to compute hash for {file_path}: {e}")
                
        self.logger.info(f"FIRST_FILE_HASH: {result or '<no files>'}")
                
    @staticmethod
    def compute_file_md5(path: str) -> str:
        CHUNK_SIZE: int = 1024 * 1024
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(partial(f.read, CHUNK_SIZE), b""):
                h.update(chunk)
        return h.hexdigest()   

    def compute_folder_hash(self, folder_path: str) -> str:
        file_hashes = []

        for file_path in sorted(folder_path.rglob("*")):
            if not file_path.is_file() or file_path.is_symlink():
                continue  

            rel_path = file_path.relative_to(folder_path).as_posix()  
            try:
                if os.access(str(file_path), os.R_OK):
                    file_hash = self.compute_file_md5(str(file_path))
                    file_hashes.append(f"{rel_path}:{file_hash}")
                else:
                    self.logger.error(f"NO READ PERMISSION (hash skipped): {file_path}")
            except (OSError, IOError) as e:
                self.logger.warning(f"Failed to hash {file_path}: {e}")
                continue

        combined = "\n".join(sorted(file_hashes))
        return hashlib.md5(combined.encode("utf-8")).hexdigest()

    @staticmethod
    def relative_items(base_dir: str) -> Tuple[Dict[str, str], Dict[str, None]]:
        base_path = Path(base_dir)
        files = {
            p.relative_to(base_path).as_posix(): str(p)
            for p in base_path.rglob("*")
            if p.is_file()
        }
        dirs = {
            p.relative_to(base_path).as_posix(): None
            for p in base_path.rglob("*")
            if p.is_dir() and not p.is_symlink()
        }
        dirs[""] = None
        return files, dirs

    def ensure_dirs(self, replica_root: str, dir_rel_paths: dict) -> None:
        root_path = Path(replica_root)
        for dest in sorted((root_path / rel if rel else root_path) for rel in dir_rel_paths):
            if os.access(dest.parent, os.W_OK):
                try:
                    dest.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"CREATE_DIR: {dest.resolve()}")
                except OSError as e:
                    self.logger.error(f"ERROR CREATE DIR: {dest}: {e}")
            else:
                self.logger.error(f"NO WRITE PERMISSION (dir not created): {dest}")

    def sync_files(self) -> None:
        source_files, source_dirs = self.relative_items(self.source)
        replica_files, _ = self.relative_items(self.replica)

        self.ensure_dirs(self.replica, source_dirs)

        for rel, src_abs in source_files.items():
            dst_abs = os.path.normpath(os.path.join(self.replica, rel))
            copy_file_with_attributes(src_abs, dst_abs, self.logger)

        for rel, dst_abs in replica_files.items():
            if rel not in source_files:
                try:
                    if os.access(dst_abs, os.W_OK):
                        os.remove(dst_abs)
                        self.logger.info(f"DELETE      : {os.path.abspath(dst_abs)}")
                    else:
                        self.logger.error(f"NO WRITE PERMISSION (cannot delete): {dst_abs}")
                except Exception as e:
                    self.logger.error(f"ERROR DELETE: {dst_abs}: {e}")

        for root, _, _ in os.walk(self.replica, topdown=False):
            rel_root = os.path.relpath(root, self.replica)
            rel = "" if rel_root == "." else rel_root.replace(os.sep, "/")
            if rel not in source_dirs:
                try:
                    if not os.listdir(root) and os.access(root, os.W_OK):
                        os.rmdir(root)
                        self.logger.info(f"DELETE_DIR  : {os.path.abspath(root)}")
                except Exception:
                    pass



    def skip_if_not_enough_space(self) -> bool:
        try:
            total, used, free = shutil.disk_usage(self.replica)
            required = self.get_directory_size(self.source)
            self.logger.debug(f"Free space: {free/1024/1024:.2f} MB, Required: {required/1024/1024:.2f} MB")
            if  free <= required:
                self.logger.error("Not enough disk space — skipping this synchronization.")
                return True
            else:
                return False 

        except Exception as e:
            self.logger.error(f"Unable to check disk space: {e}")
            return True
        
    def get_directory_size(self, directory: str) -> int:
        total = 0
        for root, _, files in os.walk(directory):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    self.logger.debug(f"Unable to check disk space for : {os.path}")
                    continue
        return total

def main() -> None:
    parser = Parser(sys.argv)
    FolderSync(*parser.run()).run()
    
if __name__ == "__main__":
    main()
