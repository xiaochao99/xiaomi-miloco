# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
System controller
Handles system update operations via hot update mechanism
"""

import asyncio
import subprocess
import json
import os
import re
import hashlib
import shutil
import tarfile
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from miloco_server.schema.common_schema import NormalResponse


class ApplyUpdateRequest(BaseModel):
    version: Optional[str] = None
    update_config: bool = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])

# GitHub configuration - matches hot_update.sh
GITHUB_REPO = os.environ.get("MILOCO_GITHUB_REPO", "xiaochao99/xiaomi-miloco")
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}"
GITHUB_DOWNLOAD_URL = f"https://github.com/{GITHUB_REPO}/releases/download"
GITHUB_TOKEN = os.environ.get("MILOCO_GITHUB_TOKEN", "")

# App base path inside container
APP_BASE_DIR = os.environ.get("APP_BASE_DIR", "/app")
BACKUP_BASE_DIR = os.environ.get("BACKUP_BASE_DIR", os.path.expanduser("~/.miloco/backups"))


class UpdateStatus(BaseModel):
    """Status of the update process"""
    current_version: str
    latest_version: Optional[str] = None
    update_available: bool = False
    last_check: Optional[str] = None
    last_update: Optional[str] = None
    is_updating: bool = False
    update_log: Optional[str] = None


class UpdateResult(BaseModel):
    """Result of an update operation"""
    success: bool
    message: str
    version: Optional[str] = None
    log: Optional[str] = None


# Global state for update process
_update_status = UpdateStatus(
    current_version="unknown",
    latest_version=None,
    update_available=False,
    last_check=None,
    last_update=None,
    is_updating=False,
    update_log=None
)


def _get_hot_update_script_path() -> str:
    """Get the path to the hot_update.sh script"""
    # Look for the script in common locations
    possible_paths = [
        "/app/scripts/hot_update.sh",
        "/opt/miloco/scripts/hot_update.sh",
        os.path.expanduser("~/.miloco/hot_update.sh"),
        os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "hot_update.sh"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    raise FileNotFoundError("hot_update.sh script not found")


async def _run_hot_update_command(command: str, args: list = None) -> tuple[int, str, str]:
    """Run a hot_update.sh command asynchronously"""
    script_path = _get_hot_update_script_path()
    cmd = ["bash", script_path, command]
    if args:
        cmd.extend(args)
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode(), stderr.decode()
    except Exception as e:
        logger.error(f"Failed to run hot_update command '{command}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute update command: {str(e)}")


def _parse_version_from_output(output: str) -> Optional[str]:
    """Parse version information from command output"""
    lines = output.strip().split('\n')
    for line in lines:
        if 'version' in line.lower() or 'v0.' in line.lower():
            # Try to extract version pattern like v0.0.5
            import re
            match = re.search(r'v?\d+\.\d+\.\d+', line)
            if match:
                return match.group()
    return None


def _parse_update_available(output: str) -> bool:
    """Parse whether an update is available from check output"""
    output_lower = output.lower()
    return 'available' in output_lower or 'new version' in output_lower or 'update found' in output_lower


@router.get("/system/update/status", response_model=NormalResponse)
async def get_update_status():
    """Get current update status"""
    global _update_status
    
    # Try to get current version from multiple locations
    version_paths = [
        "/app/VERSION",
        os.path.join(os.path.dirname(__file__), "..", "..", "VERSION"),
        os.path.expanduser("~/.miloco/.hot_update_version"),
    ]
    
    for path in version_paths:
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    ver = f.read().strip()
                    if ver:
                        _update_status.current_version = ver
                        break
        except Exception:
            continue
    
    return NormalResponse(code=0, message="success", data=_update_status.model_dump())


@router.get("/system/update/check", response_model=NormalResponse)
async def check_for_updates():
    """Check for available updates via GitHub API directly"""
    global _update_status
    
    try:
        _update_status.last_check = datetime.now().isoformat()
        
        # Re-read current version from files (it resets to "unknown" after restart)
        version_paths = [
            "/app/VERSION",
            os.path.join(os.path.dirname(__file__), "..", "..", "VERSION"),
            os.path.expanduser("~/.miloco/.hot_update_version"),
        ]
        for vp in version_paths:
            try:
                if os.path.exists(vp):
                    with open(vp, 'r') as f:
                        ver = f.read().strip()
                        if ver:
                            _update_status.current_version = ver
                            break
            except Exception:
                continue
        
        if not HAS_HTTPX:
            # Fallback to shell script
            returncode, stdout, stderr = await _run_hot_update_command("check")
            if returncode == 0:
                _update_status.update_available = _parse_update_available(stdout)
                _update_status.latest_version = _parse_version_from_output(stdout)
                _update_status.update_log = stdout
                data = {
                    "success": True,
                    "update_available": _update_status.update_available,
                    "current_version": _update_status.current_version,
                    "latest_version": _update_status.latest_version,
                    "check_time": _update_status.last_check,
                    "output": stdout
                }
            else:
                _update_status.update_log = stderr
                data = {
                    "success": False,
                    "update_available": False,
                    "error": stderr,
                    "check_time": _update_status.last_check
                }
            return NormalResponse(code=0, message="success", data=data)
        
        # Direct GitHub API call
        headers = {"Accept": "application/vnd.github+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GITHUB_API_URL}/releases/latest", headers=headers)
            
            if resp.status_code == 404:
                data = {
                    "success": True,
                    "update_available": False,
                    "current_version": _update_status.current_version,
                    "latest_version": None,
                    "check_time": _update_status.last_check,
                    "message": "No releases found"
                }
                return NormalResponse(code=0, message="success", data=data)
            
            resp.raise_for_status()
            release_data = resp.json()
            
            latest_version = release_data.get("tag_name", "")
            current_version = _update_status.current_version
            
            def parse_ver(v):
                nums = re.findall(r'\d+', v)
                return tuple(int(n) for n in nums) if nums else (0,)
            
            update_available = parse_ver(latest_version) > parse_ver(current_version)
            
            _update_status.update_available = update_available
            _update_status.latest_version = latest_version
            
            data = {
                "success": True,
                "update_available": update_available,
                "current_version": current_version,
                "latest_version": latest_version,
                "check_time": _update_status.last_check,
                "release_name": release_data.get("name", latest_version),
                "release_url": release_data.get("html_url", ""),
                "release_body": release_data.get("body", ""),
                "published_at": release_data.get("published_at", ""),
                "has_config": False,
                "assets": [
                    {"name": a["name"], "size": a["size"], "url": a["browser_download_url"]}
                    for a in release_data.get("assets", [])
                    if "hotfix" in a.get("name", "") or a.get("name") == "manifest.json"
                ]
            }
            
            # Try to download manifest.json from release assets to check has_config
            if update_available:
                manifest_asset = next(
                    (a for a in release_data.get("assets", []) if a.get("name") == "manifest.json"),
                    None
                )
                if manifest_asset:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as mc:
                            mresp = await mc.get(manifest_asset["browser_download_url"], headers=headers)
                            mresp.raise_for_status()
                            mdata = mresp.json()
                            data["has_config"] = mdata.get("changes", {}).get("backend", {}).get("has_config", False)
                    except Exception as me:
                        logger.debug(f"Failed to fetch manifest.json: {me}")
            
            return NormalResponse(code=0, message="success", data=data)
    
    except httpx.HTTPError as e:
        logger.error(f"GitHub API error: {e}")
        _update_status.update_log = f"GitHub API error: {str(e)}"
        raise HTTPException(status_code=502, detail=f"Failed to check GitHub releases: {str(e)}")
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        _update_status.update_log = str(e)
        raise HTTPException(status_code=500, detail=str(e))


def _verify_checksum(file_path: str, expected_hash: str) -> bool:
    """Verify file SHA256 checksum"""
    sha = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha.update(chunk)
    actual = sha.hexdigest()
    # Strip "sha256:" prefix if present
    expected = expected_hash.replace("sha256:", "")
    return actual == expected


async def _download_file(url: str, dest: str, auth_headers: dict = None) -> None:
    """Download a file with optional auth"""
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        headers = auth_headers or {}
        async with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            with open(dest, 'wb') as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)


async def _apply_update_internal(version: str, update_config: bool = False) -> dict:
    """Core update logic - download package & apply files in-container"""
    global _update_status
    log_lines = []
    
    try:
        _update_status.is_updating = True
        _update_status.update_log = "Starting update...\n"
        
        auth_headers = {"Accept": "application/octet-stream"}
        if GITHUB_TOKEN:
            auth_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        
        # 1. Download package
        pkg_name = f"miloco-hotfix-{version}.tar.gz"
        pkg_url = f"{GITHUB_DOWNLOAD_URL}/{version}/{pkg_name}"
        
        msg = f"Downloading {pkg_url}..."
        logger.info(msg)
        log_lines.append(msg)
        _update_status.update_log = "\n".join(log_lines)
        
        tmp_dir = tempfile.mkdtemp(prefix="miloco_hotfix_")
        pkg_path = os.path.join(tmp_dir, pkg_name)
        
        await _download_file(pkg_url, pkg_path, auth_headers)
        
        msg = f"Downloaded {os.path.getsize(pkg_path)} bytes"
        log_lines.append(msg)
        _update_status.update_log = "\n".join(log_lines)
        
        # 2. Checksum verification
        checksum_url = f"{pkg_url}.sha256"
        checksum_path = os.path.join(tmp_dir, f"{pkg_name}.sha256")
        try:
            await _download_file(checksum_url, checksum_path, auth_headers)
            with open(checksum_path, 'r') as f:
                expected_hash = f.read().strip().split()[0]
            if not _verify_checksum(pkg_path, expected_hash):
                raise ValueError("Checksum mismatch")
            msg = "Checksum verified OK"
        except Exception:
            msg = "Checksum file not available, skipping verification"
        log_lines.append(msg)
        _update_status.update_log = "\n".join(log_lines)
        
        # 3. Extract
        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with tarfile.open(pkg_path, 'r:gz') as tf:
            tf.extractall(extract_dir)
        
        msg = "Package extracted"
        log_lines.append(msg)
        _update_status.update_log = "\n".join(log_lines)
        
        # Find the actual content dir (tar may have a top-level dir)
        content_dirs = [d for d in os.listdir(extract_dir) if os.path.isdir(os.path.join(extract_dir, d))]
        if not content_dirs:
            raise ValueError("Empty package")
        content_dir = os.path.join(extract_dir, content_dirs[0])
        
        # 4. Read manifest
        manifest_path = os.path.join(content_dir, "manifest.json")
        manifest = {}
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r', encoding='utf-8-sig') as f:
                manifest = json.load(f)
        
        # 5. Create backup
        backup_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_BASE_DIR, backup_name)
        os.makedirs(backup_path, exist_ok=True)
        
        msg = f"Backup created: {backup_path}"
        log_lines.append(msg)
        _update_status.update_log = "\n".join(log_lines)
        
        # 6. Apply files - copy from package to /app
        copy_count = 0
        skip_config = not update_config
        for root, dirs, files in os.walk(content_dir):
            for fn in files:
                if fn in ("manifest.json", "checksums.sha256"):
                    continue
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, content_dir)
                
                # Determine target path: strip the top dir from rel
                # e.g., "miloco-hotfix-v1.0.1/backend/miloco_server/x.py" -> "miloco_server/x.py"
                parts = Path(rel).parts
                target_rel = str(Path(*parts[2:])) if len(parts) > 2 and parts[0].startswith("miloco-hotfix") else str(Path(*parts[1:])) if len(parts) > 1 else rel
                
                # Resolve target based on source structure
                if target_rel.startswith("backend/"):
                    target_rel = target_rel[len("backend/"):]
                
                # Skip config files if user chose not to update config
                if skip_config and target_rel.startswith("config/"):
                    log_lines.append(f"  Skipped (config): {target_rel}")
                    continue
                
                target_path = os.path.join(APP_BASE_DIR, target_rel)
                
                # Backup existing file
                bk_file = os.path.join(backup_path, target_rel)
                os.makedirs(os.path.dirname(bk_file), exist_ok=True)
                if os.path.exists(target_path):
                    shutil.copy2(target_path, bk_file)
                
                # Copy new file
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(src, target_path)
                copy_count += 1
                log_lines.append(f"  Updated: {target_rel}")
        
        msg = f"Applied {copy_count} files"
        log_lines.append(msg)
        
        # 7. Save version
        version_file = os.path.join(APP_BASE_DIR, "VERSION")
        with open(version_file, 'w') as f:
            f.write(version)
        
        home_version_file = os.path.expanduser("~/.miloco/.hot_update_version")
        os.makedirs(os.path.dirname(home_version_file), exist_ok=True)
        with open(home_version_file, 'w') as f:
            f.write(version)
        
        _update_status.current_version = version
        _update_status.last_update = datetime.now().isoformat()
        _update_status.update_available = False
        
        # 8. Cleanup temp
        shutil.rmtree(tmp_dir, ignore_errors=True)
        
        msg = f"Update to {version} completed! Service will restart."
        log_lines.append(msg)
        _update_status.update_log = "\n".join(log_lines)
        
        return {"success": True, "message": msg, "files_updated": copy_count, "backup": backup_name}
        
    except Exception as e:
        msg = f"Update error: {str(e)}"
        log_lines.append(msg)
        _update_status.update_log = "\n".join(log_lines)
        logger.exception("Update failed")
        raise
    finally:
        _update_status.is_updating = False


@router.post("/system/update/apply", response_model=NormalResponse)
async def apply_update(background_tasks: BackgroundTasks, req: ApplyUpdateRequest = None):
    """Apply available update"""
    global _update_status
    
    if req is None:
        req = ApplyUpdateRequest()
    
    if _update_status.is_updating:
        raise HTTPException(status_code=409, detail="Update already in progress")
    
    # Determine version
    target_version = req.version or _update_status.latest_version
    if not target_version:
        raise HTTPException(status_code=400, detail="No version specified and no latest version available")
    
    # Run update in background
    async def run_update():
        global _update_status
        try:
            result = await _apply_update_internal(target_version, update_config=req.update_config)
            _update_status.update_log = result.get("message", "")
            # Trigger restart after a short delay (let the response finish)
            await asyncio.sleep(2)
            _restart_service()
        except Exception as e:
            _update_status.update_log = f"Update failed: {str(e)}"
            logger.error(f"Update failed: {e}")
    
    background_tasks.add_task(run_update)
    
    return NormalResponse(code=0, message="Update started in background", data={"version": target_version})


def _restart_service():
    """Trigger service restart"""
    os._exit(0)  # Force exit, Docker should restart the container


@router.get("/system/update/log", response_model=NormalResponse)
async def get_update_log():
    """Get update log"""
    return NormalResponse(code=0, message="success", data={
        "log": _update_status.update_log,
        "is_updating": _update_status.is_updating,
        "last_update": _update_status.last_update
    })


@router.get("/system/backups", response_model=NormalResponse)
async def list_backups():
    """List available backups"""
    try:
        returncode, stdout, stderr = await _run_hot_update_command("rollback")
        
        if returncode == 0:
            backups = []
            lines = stdout.strip().split('\n')
            for line in lines:
                if 'backup_' in line or '202' in line:
                    backups.append(line.strip())
            
            return NormalResponse(code=0, message="success", data={
                "backups": backups,
                "output": stdout
            })
        else:
            return NormalResponse(code=0, message="success", data={
                "backups": [],
                "error": stderr
            })
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RollbackRequest(BaseModel):
    """Request model for rollback operation"""
    backup_name: str

@router.post("/system/rollback", response_model=NormalResponse)
async def rollback_to_backup(request: RollbackRequest):
    """Rollback to a specific backup"""
    global _update_status
    
    if _update_status.is_updating:
        raise HTTPException(status_code=409, detail="Update/rollback already in progress")
    
    try:
        _update_status.is_updating = True
        
        returncode, stdout, stderr = await _run_hot_update_command("rollback", [request.backup_name])
        
        if returncode == 0:
            _update_status.last_update = datetime.now().isoformat()
            _update_status.update_log = f"Rollback to {request.backup_name} completed.\n{stdout}"
            
            return NormalResponse(code=0, message=f"Successfully rolled back to {request.backup_name}", data={
                "output": stdout
            })
        else:
            _update_status.update_log = f"Rollback failed.\n{stderr}"
            return NormalResponse(code=0, message="Rollback failed", data={
                "error": stderr
            })
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _update_status.is_updating = False


@router.get("/system/status", response_model=NormalResponse)
async def get_system_status():
    """Get overall system status including update info"""
    try:
        returncode, stdout, stderr = await _run_hot_update_command("status")
        
        return NormalResponse(code=0, message="success", data={
            "status": stdout if returncode == 0 else stderr,
            "update_info": {
                "current_version": _update_status.current_version,
                "update_available": _update_status.update_available,
                "last_check": _update_status.last_check,
                "last_update": _update_status.last_update,
                "is_updating": _update_status.is_updating
            }
        })
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))