# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Music Controller - REST API endpoints for music player module.
音乐控制器 - 音乐播放器的 REST API 端点
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Body, Response
from fastapi.responses import FileResponse, StreamingResponse

from miloco_server.schema.music_schema import (
    Song,
    Playlist,
    PlaybackStatus,
    DLNADevice,
    MusicControlRequest,
    MusicSearchRequest,
    MusicSearchResult,
    DLNADiscoverRequest,
    DLNACastRequest,
    LocalMusicScanRequest,
    LocalMusicScanResult,
)
from miloco_server.schema.common_schema import NormalResponse
from miloco_server.service.music_service import get_music_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/music", tags=["music"])


@router.get("/songs", response_model=NormalResponse)
async def get_all_songs():
    """
    获取所有歌曲列表
    """
    try:
        service = get_music_service()
        songs = service.get_all_songs()
        return NormalResponse(
            code=0,
            message="success",
            data=[song.model_dump() for song in songs]
        )
    except Exception as e:
        logger.error("Failed to get songs: %s", e)
        return NormalResponse(code=500, message=f"获取歌曲列表失败: {str(e)}", data=None)


@router.get("/songs/{song_id}", response_model=NormalResponse)
async def get_song(song_id: str):
    """
    获取指定歌曲详情
    """
    try:
        service = get_music_service()
        song = service.get_song(song_id)
        if not song:
            return NormalResponse(code=404, message="歌曲不存在", data=None)
        return NormalResponse(code=0, message="success", data=song.model_dump())
    except Exception as e:
        logger.error("Failed to get song: %s", e)
        return NormalResponse(code=500, message=f"获取歌曲失败: {str(e)}", data=None)


@router.post("/search", response_model=NormalResponse)
async def search_songs(request: MusicSearchRequest):
    """
    搜索歌曲
    """
    try:
        service = get_music_service()
        result = service.search_songs(request)
        return NormalResponse(
            code=0,
            message="success",
            data={
                "songs": [song.model_dump() for song in result.songs],
                "total": result.total,
            }
        )
    except Exception as e:
        logger.error("Failed to search songs: %s", e)
        return NormalResponse(code=500, message=f"搜索失败: {str(e)}", data=None)


@router.get("/playlists", response_model=NormalResponse)
async def get_all_playlists():
    """
    获取所有播放列表
    """
    try:
        service = get_music_service()
        playlists = service.get_all_playlists()
        return NormalResponse(
            code=0,
            message="success",
            data=[playlist.model_dump() for playlist in playlists]
        )
    except Exception as e:
        logger.error("Failed to get playlists: %s", e)
        return NormalResponse(code=500, message=f"获取播放列表失败: {str(e)}", data=None)


@router.get("/status", response_model=NormalResponse)
async def get_playback_status():
    """
    获取当前播放状态
    """
    try:
        service = get_music_service()
        status = service.get_playback_status()
        return NormalResponse(code=0, message="success", data=status.model_dump())
    except Exception as e:
        logger.error("Failed to get playback status: %s", e)
        return NormalResponse(code=500, message=f"获取播放状态失败: {str(e)}", data=None)


@router.post("/control", response_model=NormalResponse)
async def control_playback(request: MusicControlRequest):
    """
    控制播放 (播放/暂停/停止/上下首/音量等)
    """
    try:
        service = get_music_service()
        status = service.control_playback(request)
        return NormalResponse(code=0, message="success", data=status.model_dump())
    except Exception as e:
        logger.error("Failed to control playback: %s", e)
        return NormalResponse(code=500, message=f"控制播放失败: {str(e)}", data=None)


@router.get("/dlna/devices", response_model=NormalResponse)
async def get_dlna_devices():
    """
    获取已发现的DLNA设备列表
    """
    try:
        service = get_music_service()
        devices = service.get_dlna_devices()
        return NormalResponse(
            code=0,
            message="success",
            data=[device.model_dump() for device in devices]
        )
    except Exception as e:
        logger.error("Failed to get DLNA devices: %s", e)
        return NormalResponse(code=500, message=f"获取DLNA设备失败: {str(e)}", data=None)


@router.post("/dlna/discover", response_model=NormalResponse)
async def discover_dlna_devices(request: DLNADiscoverRequest = Body(default=DLNADiscoverRequest())):
    """
    发现局域网内的DLNA设备
    """
    try:
        service = get_music_service()
        devices = await service.discover_dlna_devices(request.timeout)
        return NormalResponse(
            code=0,
            message="success",
            data={
                "devices": [device.model_dump() for device in devices],
                "total": len(devices),
            }
        )
    except Exception as e:
        logger.error("Failed to discover DLNA devices: %s", e)
        return NormalResponse(code=500, message=f"DLNA设备发现失败: {str(e)}", data=None)


@router.post("/dlna/cast", response_model=NormalResponse)
async def cast_to_dlna(request: DLNACastRequest):
    """
    投屏音频到DLNA设备
    """
    try:
        service = get_music_service()
        success = await service.cast_to_dlna(request)
        if success:
            return NormalResponse(code=0, message="投屏成功", data=None)
        else:
            return NormalResponse(code=500, message="投屏失败", data=None)
    except Exception as e:
        logger.error("Failed to cast to DLNA: %s", e)
        return NormalResponse(code=500, message=f"投屏失败: {str(e)}", data=None)


@router.post("/dlna/stop", response_model=NormalResponse)
async def stop_dlna_cast(device_id: str = Body(..., embed=True)):
    """
    停止DLNA投屏
    """
    try:
        service = get_music_service()
        success = await service.stop_dlna_cast(device_id)
        if success:
            return NormalResponse(code=0, message="停止投屏成功", data=None)
        else:
            return NormalResponse(code=500, message="停止投屏失败", data=None)
    except Exception as e:
        logger.error("Failed to stop DLNA cast: %s", e)
        return NormalResponse(code=500, message=f"停止投屏失败: {str(e)}", data=None)


# ─── Scan Directory Management ────────────────────

@router.get("/scan/dirs", response_model=NormalResponse)
async def get_scan_dirs():
    """获取扫描目录列表"""
    try:
        service = get_music_service()
        dirs = service.get_scan_dirs()
        return NormalResponse(code=0, message="success", data=dirs)
    except Exception as e:
        logger.error("Failed to get scan dirs: %s", e)
        return NormalResponse(code=500, message=str(e), data=None)


@router.post("/scan/dirs", response_model=NormalResponse)
async def add_scan_dir(
    path: str = Body(..., embed=True),
    name: str = Body(default="", embed=True),
    recursive: bool = Body(default=True, embed=True),
):
    """添加扫描目录"""
    try:
        service = get_music_service()
        entry = service.add_scan_dir(path, name, recursive)
        return NormalResponse(code=0, message="添加成功", data=entry)
    except Exception as e:
        logger.error("Failed to add scan dir: %s", e)
        return NormalResponse(code=500, message=str(e), data=None)


@router.delete("/scan/dirs/{dir_id}", response_model=NormalResponse)
async def remove_scan_dir(dir_id: str):
    """删除扫描目录"""
    try:
        service = get_music_service()
        ok = service.remove_scan_dir(dir_id)
        if ok:
            return NormalResponse(code=0, message="删除成功", data=None)
        return NormalResponse(code=404, message="目录不存在", data=None)
    except Exception as e:
        logger.error("Failed to remove scan dir: %s", e)
        return NormalResponse(code=500, message=str(e), data=None)


@router.put("/scan/dirs/{dir_id}", response_model=NormalResponse)
async def update_scan_dir(dir_id: str, data: dict = Body(...)):
    """更新扫描目录配置"""
    try:
        service = get_music_service()
        entry = service.update_scan_dir(dir_id, **data)
        if entry:
            return NormalResponse(code=0, message="更新成功", data=entry)
        return NormalResponse(code=404, message="目录不存在", data=None)
    except Exception as e:
        logger.error("Failed to update scan dir: %s", e)
        return NormalResponse(code=500, message=str(e), data=None)


@router.post("/scan/local", response_model=NormalResponse)
async def scan_local_music(request: LocalMusicScanRequest):
    """
    扫描本地目录中的音乐文件
    
    - **path**: 要扫描的目录绝对路径
    - **recursive**: 是否递归扫描子目录，默认为true
    """
    try:
        service = get_music_service()
        result = service.scan_local_music(request)
        
        if result.errors:
            logger.warning("Scan warnings: %s", result.errors)
        
        return NormalResponse(
            code=0,
            message=f"扫描完成，发现 {result.total} 首歌曲",
            data={
                "songs": [song.model_dump() for song in result.songs],
                "total": result.total,
                "scan_path": result.scan_path,
                "errors": result.errors,
            }
        )
    except Exception as e:
        logger.error("Failed to scan local music: %s", e)
        return NormalResponse(code=500, message=f"扫描失败: {str(e)}", data=None)


@router.get("/stream/{song_id}")
async def stream_audio(song_id: str):
    """
    流式播放音频文件
    
    - **song_id**: 歌曲ID
    """
    try:
        service = get_music_service()
        file_path = service.get_audio_file_path(song_id)
        
        if not file_path:
            # 检查是否是演示歌曲
            song = service.get_song(song_id)
            if song and song.audio_url.startswith('/api/music/stream/'):
                return NormalResponse(code=404, message="演示歌曲不支持流媒体播放", data=None)
            return NormalResponse(code=404, message="歌曲文件不存在", data=None)
        
        import os
        if not os.path.exists(file_path):
            return NormalResponse(code=404, message="音频文件不存在", data=None)
        
        # 根据文件扩展名设置MIME类型
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "audio/mpeg"
        
        return FileResponse(
            path=file_path,
            media_type=mime_type,
            filename=os.path.basename(file_path),
        )
    except Exception as e:
        logger.error("Failed to stream audio: %s", e)
        return NormalResponse(code=500, message=f"播放失败: {str(e)}", data=None)


@router.get("/cover/{song_id}")
async def get_cover(song_id: str):
    """
    获取歌曲封面图片（从磁盘缓存读取，扫描时已提取保存）
    """
    try:
        service = get_music_service()
        covers_dir = service._covers_dir

        # 查找已保存的封面文件
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            cover_path = covers_dir / f"{song_id}{ext}"
            if cover_path.exists():
                mime = 'image/jpeg' if ext in ['.jpg', '.jpeg'] else f'image/{ext[1:]}'
                return FileResponse(
                    path=str(cover_path),
                    media_type=mime,
                    headers={"Cache-Control": "public, max-age=604800"},
                )

        # 没有已保存的封面，尝试实时提取
        file_path = service.get_audio_file_path(song_id)
        if not file_path:
            return Response(status_code=404)

        from pathlib import Path
        p = Path(file_path)
        if not p.exists():
            return Response(status_code=404)

        cover_bytes, mime = service.extract_cover_bytes(p)
        if not cover_bytes:
            return Response(status_code=204)

        # 保存到磁盘供后续使用
        ext = '.png' if mime and 'png' in mime else '.jpg'
        cover_path = covers_dir / f"{song_id}{ext}"
        try:
            cover_path.write_bytes(cover_bytes)
        except Exception:
            pass

        return Response(
            content=cover_bytes,
            media_type=mime,
            headers={"Cache-Control": "public, max-age=604800"},
        )
    except Exception as e:
        logger.error("Failed to get cover for %s: %s", song_id, e)
        return Response(status_code=500)


@router.get("/lyric/{song_id}")
async def get_lyric(song_id: str):
    """
    获取歌曲歌词 JSON（从磁盘缓存读取）
    """
    try:
        import json
        service = get_music_service()
        lyrics = service.get_lyrics_from_disk(song_id)
        if lyrics:
            data = [{"time": l.time, "text": l.text} for l in lyrics]
            return Response(
                content=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                media_type="application/json",
                headers={"Cache-Control": "public, max-age=604800"},
            )

        # Fallback: try extracting from audio file
        file_path = service.get_audio_file_path(song_id)
        if not file_path:
            return Response(status_code=404)

        from pathlib import Path
        p = Path(file_path)
        if not p.exists():
            return Response(status_code=404)

        lyrics = service._extract_lyrics(p, None)
        if lyrics:
            service._save_lyrics(song_id, lyrics)
            data = [{"time": l.time, "text": l.text} for l in lyrics]
            return Response(
                content=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                media_type="application/json",
                headers={"Cache-Control": "public, max-age=604800"},
            )

        return Response(status_code=204)
    except Exception as e:
        logger.error("Failed to get lyrics for %s: %s", song_id, e)
        return Response(status_code=500)


@router.get("/command", response_model=NormalResponse)
async def get_music_commands(since_id: int = Query(0, description="Last processed command ID")):
    """
    获取待处理的音乐控制命令 (前端轮询使用)
    MCP 工具将命令写入队列，前端通过此接口轮询获取并执行
    """
    try:
        service = get_music_service()
        commands = service.pop_commands(since_id)
        # Always return the max known command ID so the client advances
        cmd_ids = [cmd["id"] for cmd in commands]
        max_id = max(cmd_ids + [since_id, service._command_id_counter])
        return NormalResponse(
            code=0,
            message="success",
            data={
                "commands": commands,
                "last_id": max_id,
            }
        )
    except Exception as e:
        logger.error("Failed to get music commands: %s", e)
        return NormalResponse(code=500, message=f"获取命令失败: {str(e)}", data=None)


@router.post("/command", response_model=NormalResponse)
async def push_music_command(
    action: str = Body(..., embed=True),
    params: dict = Body(default={}, embed=True),
):
    """
    推送音乐控制命令到队列 (MCP 工具使用)
    """
    try:
        service = get_music_service()
        cmd_id = service.push_command(action, params)
        return NormalResponse(
            code=0,
            message="命令已推送",
            data={"command_id": cmd_id}
        )
    except Exception as e:
        logger.error("Failed to push music command: %s", e)
        return NormalResponse(code=500, message=f"推送命令失败: {str(e)}", data=None)


@router.get("/playlists/{playlist_id}", response_model=NormalResponse)
async def get_playlist(playlist_id: str):
    """
    获取指定播放列表详情
    """
    try:
        service = get_music_service()
        playlists = service.get_all_playlists()
        playlist = next((p for p in playlists if p.id == playlist_id), None)
        
        if not playlist:
            return NormalResponse(code=404, message="播放列表不存在", data=None)
        
        return NormalResponse(
            code=0,
            message="success",
            data=playlist.model_dump()
        )
    except Exception as e:
        logger.error("Failed to get playlist: %s", e)
        return NormalResponse(code=500, message=f"获取播放列表失败: {str(e)}", data=None)


# ─── File Watcher (stubs) ─────────────────────────

@router.get("/watcher/status", response_model=NormalResponse)
async def get_watcher_status():
    """获取文件监控状态"""
    return NormalResponse(code=0, message="success", data={"running": False})


@router.post("/watcher/start", response_model=NormalResponse)
async def start_watcher():
    """启动文件监控"""
    return NormalResponse(code=0, message="文件监控已启动", data=None)


@router.post("/watcher/stop", response_model=NormalResponse)
async def stop_watcher():
    """停止文件监控"""
    return NormalResponse(code=0, message="文件监控已停止", data=None)
