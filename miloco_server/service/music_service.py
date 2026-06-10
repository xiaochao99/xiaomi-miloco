# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Music Service - Business logic layer for music player module.
音乐服务层 - 音乐播放器的业务逻辑管理
"""

import logging
import uuid
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from datetime import datetime

from miloco_server.schema.music_schema import (
    Song,
    Playlist,
    LyricLine,
    PlaybackState,
    RepeatMode,
    PlaybackStatus,
    DLNADevice,
    MusicControlAction,
    MusicControlRequest,
    MusicSearchRequest,
    MusicSearchResult,
    DLNACastRequest,
    LocalMusicScanRequest,
    LocalMusicScanResult,
)
from miloco_server.dlna.dlna_service import DLNAService, get_dlna_service

logger = logging.getLogger(__name__)

_music_service_instance: Optional["MusicService"] = None

# 示例歌曲数据 (实际项目中应从数据库或文件系统读取)
_DEMO_SONGS: list = []


class MusicService:
    """
    音乐服务
    提供音乐播放器的业务逻辑管理
    """

    def __init__(self, dlna_service: Optional[DLNAService] = None):
        self._dlna_service = dlna_service or get_dlna_service()
        self._songs: Dict[str, Song] = {}
        self._playlists: Dict[str, Playlist] = {}
        self._playback_status = PlaybackStatus()
        self._initialized = False

        # Command queue for frontend polling
        self._command_queue: List[Dict[str, Any]] = []
        self._command_id_counter = 0
        self._file_path_map: Dict[str, str] = {}

        # Persistent storage directory
        self._data_dir = Path(__file__).parent.parent / "data" / "music"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._songs_file = self._data_dir / "songs.json"
        self._dirs_file = self._data_dir / "scan_dirs.json"
        self._covers_dir = self._data_dir / "covers"
        self._covers_dir.mkdir(parents=True, exist_ok=True)
        self._lyrics_dir = self._data_dir / "lyrics"
        self._lyrics_dir.mkdir(parents=True, exist_ok=True)

        # Scan directories
        self._scan_dirs: List[Dict[str, Any]] = []
        self._load_scan_dirs()

        # 初始化示例数据 + 加载持久化的歌曲
        self._init_demo_data()
        self._load_persisted_songs()

    # ─── Command Queue (for frontend polling) ──────

    def push_command(self, action: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        Push a command to the queue for the frontend to consume.

        Args:
            action: Command action (play, pause, next, previous, play_song, search_and_play, set_volume, etc.)
            params: Additional parameters

        Returns:
            Command ID
        """
        self._command_id_counter += 1
        cmd = {
            "id": self._command_id_counter,
            "action": action,
            "params": params or {},
            "timestamp": __import__('time').time(),
        }
        self._command_queue.append(cmd)
        # Keep queue bounded
        if len(self._command_queue) > 100:
            self._command_queue = self._command_queue[-50:]
        logger.info("Music command queued: %s %s", action, params)
        return cmd["id"]

    def pop_commands(self, since_id: int = 0) -> List[Dict[str, Any]]:
        """
        Get all commands with ID > since_id. Called by frontend polling.

        Args:
            since_id: Last command ID the frontend processed

        Returns:
            List of pending commands
        """
        return [cmd for cmd in self._command_queue if cmd["id"] > since_id]

    def clear_commands(self):
        """Clear all commands from the queue."""
        self._command_queue.clear()

    def _init_demo_data(self):
        """初始化示例数据"""
        for song in _DEMO_SONGS:
            self._songs[song.id] = song

        # 创建默认播放列表
        default_playlist = Playlist(
            id="playlist_default",
            name="默认播放列表",
            songs=_DEMO_SONGS,
        )
        self._playlists[default_playlist.id] = default_playlist

        # 设置播放列表
        self._playback_status.playlist = default_playlist
        if _DEMO_SONGS:
            self._playback_status.current_song = _DEMO_SONGS[0]
            self._playback_status.current_index = 0

        self._initialized = True
        logger.info("MusicService initialized with %d songs", len(self._songs))

    # ─── Persistent Storage ──────────────────────────

    def _load_persisted_songs(self):
        """Load scanned songs from disk on startup."""
        if not self._songs_file.exists():
            return
        try:
            import json
            with open(self._songs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = 0
            for item in data:
                song = Song(
                    id=item["id"],
                    title=item.get("title", "未知歌曲"),
                    artist=item.get("artist", "未知歌手"),
                    album=item.get("album", "未知专辑"),
                    duration=item.get("duration", 0),
                    cover_url=item.get("cover_url", ""),
                    audio_url=item.get("audio_url", ""),
                    lyrics=[LyricLine(time=l["time"], text=l["text"]) for l in item.get("lyrics", [])],
                )
                self._songs[song.id] = song
                # Restore file path mapping
                fp = item.get("file_path")
                if fp:
                    self._file_path_map[song.id] = fp
                count += 1
            # Verify file paths still exist
            valid = 0
            for sid, fp in list(self._file_path_map.items()):
                if os.path.exists(fp):
                    valid += 1
                else:
                    del self._file_path_map[sid]
                    if sid in self._songs:
                        del self._songs[sid]
            logger.info("Loaded %d persisted songs, %d files still exist", count, valid)
        except Exception as e:
            logger.error("Failed to load persisted songs: %s", e)

    def _save_persisted_songs(self):
        """Save scanned songs (local_ prefix) to disk."""
        try:
            import json
            local_songs = [
                {
                    "id": s.id,
                    "title": s.title,
                    "artist": s.artist,
                    "album": s.album,
                    "duration": s.duration,
                    "audio_url": s.audio_url,
                    "lyrics": [{"time": l.time, "text": l.text} for l in (s.lyrics or [])],
                    "file_path": self._file_path_map.get(s.id, ""),
                }
                for s in self._songs.values()
                if s.id.startswith("local_")
            ]
            with open(self._songs_file, "w", encoding="utf-8") as f:
                json.dump(local_songs, f, ensure_ascii=False, indent=2)
            logger.info("Persisted %d local songs to disk", len(local_songs))
        except Exception as e:
            logger.error("Failed to persist songs: %s", e)

    def _load_scan_dirs(self):
        """Load scan directory config from disk."""
        if not self._dirs_file.exists():
            return
        try:
            import json
            with open(self._dirs_file, "r", encoding="utf-8") as f:
                self._scan_dirs = json.load(f)
        except Exception as e:
            logger.error("Failed to load scan dirs: %s", e)

    def _save_scan_dirs(self):
        """Save scan directory config to disk."""
        try:
            import json
            with open(self._dirs_file, "w", encoding="utf-8") as f:
                json.dump(self._scan_dirs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save scan dirs: %s", e)

    # ─── Scan Directory Management ──────────────────

    def get_scan_dirs(self) -> List[Dict[str, Any]]:
        return self._scan_dirs

    def add_scan_dir(self, path: str, name: str = "", recursive: bool = True) -> Dict[str, Any]:
        import uuid
        entry = {
            "id": str(uuid.uuid4())[:8],
            "name": name or Path(path).name,
            "path": path,
            "recursive": recursive,
            "last_scan": None,
        }
        self._scan_dirs.append(entry)
        self._save_scan_dirs()
        return entry

    def remove_scan_dir(self, dir_id: str) -> bool:
        before = len(self._scan_dirs)
        self._scan_dirs = [d for d in self._scan_dirs if d["id"] != dir_id]
        if len(self._scan_dirs) < before:
            self._save_scan_dirs()
            return True
        return False

    def update_scan_dir(self, dir_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        for d in self._scan_dirs:
            if d["id"] == dir_id:
                d.update(kwargs)
                self._save_scan_dirs()
                return d
        return None

    def update_scan_dir_last_scan(self, dir_id: str):
        for d in self._scan_dirs:
            if d["id"] == dir_id:
                d["last_scan"] = datetime.now().isoformat()
                self._save_scan_dirs()
                break

    async def initialize(self) -> bool:
        """初始化服务"""
        if self._initialized:
            return True
        try:
            self._init_demo_data()
            return True
        except Exception as e:
            logger.error("MusicService initialization failed: %s", e)
            return False

    def get_all_songs(self) -> List[Song]:
        """获取所有歌曲"""
        return list(self._songs.values())

    def get_song(self, song_id: str) -> Optional[Song]:
        """根据ID获取歌曲"""
        return self._songs.get(song_id)

    def search_songs(self, request: MusicSearchRequest) -> MusicSearchResult:
        """搜索歌曲"""
        keyword = request.keyword.lower()
        results = []

        for song in self._songs.values():
            if (keyword in song.title.lower() or
                keyword in song.artist.lower() or
                keyword in song.album.lower()):
                results.append(song)

        return MusicSearchResult(songs=results, total=len(results))

    async def search_online_music(self, keyword: str, count: int = 20, source: str = "netease") -> List[Dict[str, Any]]:
        """
        搜索在线音乐 (通过 GDStudio API)

        Args:
            keyword: 搜索关键词
            count: 返回数量
            source: 音源 (netease/qq/migu)

        Returns:
            歌曲列表
        """
        import aiohttp

        base_url = "https://music-api.gdstudio.xyz/api.php"
        params = {
            "types": "search",
            "source": source,
            "name": keyword,
            "count": count,
            "pages": 1,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.error("Online music search failed: HTTP %s", resp.status)
                        return []
                    data = await resp.json()
                    if not isinstance(data, list):
                        return []

                    songs = []
                    for item in data:
                        songs.append({
                            "id": str(item.get("id", "")),
                            "title": item.get("name", "未知歌曲"),
                            "artist": " / ".join(item.get("artist", [])) if isinstance(item.get("artist"), list) else (item.get("artist") or "未知歌手"),
                            "album": item.get("album", "未知专辑"),
                            "pic_id": item.get("pic_id", ""),
                            "lyric_id": item.get("lyric_id", str(item.get("id", ""))),
                            "source": item.get("source", source),
                        })
                    return songs
        except Exception as e:
            logger.error("Online music search error: %s", e)
            return []

    async def get_online_song_url(self, track_id: str, source: str = "netease", br: int = 320) -> Optional[str]:
        """获取在线歌曲播放地址"""
        import aiohttp

        base_url = "https://music-api.gdstudio.xyz/api.php"
        params = {
            "types": "url",
            "source": source,
            "id": track_id,
            "br": br,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    return data.get("url") if data else None
        except Exception as e:
            logger.error("Get online song URL error: %s", e)
            return None

    async def get_online_song_pic(self, pic_id: str, source: str = "netease") -> Optional[str]:
        """获取在线歌曲封面"""
        import aiohttp

        base_url = "https://music-api.gdstudio.xyz/api.php"
        params = {
            "types": "pic",
            "source": source,
            "id": pic_id,
            "size": 300,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    return data.get("url") if data else None
        except Exception as e:
            logger.error("Get online song pic error: %s", e)
            return None

    async def search_and_play_online(self, keyword: str, source: str = "netease") -> Dict[str, Any]:
        """
        搜索在线音乐并添加到播放列表

        Args:
            keyword: 搜索关键词
            source: 音源

        Returns:
            搜索结果和播放状态
        """
        songs = await self.search_online_music(keyword, count=10, source=source)
        if not songs:
            return {"success": False, "error": f"未找到与 '{keyword}' 相关的歌曲", "songs": []}

        # 将搜索结果转为 Song 对象并添加到播放列表
        song_objects = []
        for s in songs:
            song = Song(
                id=f"online_{s['id']}",
                title=s["title"],
                artist=s["artist"],
                album=s["album"],
                duration=0,
                cover_url="",
                audio_url="",
                lyrics=[],
            )
            song_objects.append(song)
            self._songs[song.id] = song

        # 添加到默认播放列表
        if "playlist_default" in self._playlists:
            existing_ids = {s.id for s in self._playlists["playlist_default"].songs}
            for song in song_objects:
                if song.id not in existing_ids:
                    self._playlists["playlist_default"].songs.append(song)

        return {
            "success": True,
            "songs": songs,
            "total": len(songs),
            "message": f"找到 {len(songs)} 首歌曲，已添加到播放列表",
        }

    def get_playback_status(self) -> PlaybackStatus:
        """获取当前播放状态"""
        return self._playback_status

    def control_playback(self, request: MusicControlRequest) -> PlaybackStatus:
        """
        控制播放
        
        Args:
            request: 控制请求
            
        Returns:
            更新后的播放状态
        """
        action = request.action

        if action == MusicControlAction.PLAY:
            self._play()
        elif action == MusicControlAction.PAUSE:
            self._pause()
        elif action == MusicControlAction.STOP:
            self._stop()
        elif action == MusicControlAction.NEXT:
            self._next()
        elif action == MusicControlAction.PREVIOUS:
            self._previous()
        elif action == MusicControlAction.SEEK:
            if request.position is not None:
                self._seek(request.position)
        elif action == MusicControlAction.SET_VOLUME:
            if request.volume is not None:
                self._set_volume(request.volume)
        elif action == MusicControlAction.TOGGLE_MUTE:
            self._toggle_mute()
        elif action == MusicControlAction.SET_REPEAT:
            if request.repeat_mode:
                self._set_repeat(request.repeat_mode)
        elif action == MusicControlAction.TOGGLE_SHUFFLE:
            self._toggle_shuffle()
        elif action == MusicControlAction.PLAY_SONG:
            if request.song_id:
                self._play_song(request.song_id)
        elif action == MusicControlAction.PLAY_PLAYLIST:
            if request.playlist_id:
                self._play_playlist(request.playlist_id)

        return self._playback_status

    def _play(self):
        """播放"""
        if self._playback_status.state == PlaybackState.PAUSED:
            self._playback_status.state = PlaybackState.PLAYING
            logger.info("Resumed playback")
        elif self._playback_status.state == PlaybackState.STOPPED:
            if self._playback_status.current_song:
                self._playback_status.state = PlaybackState.PLAYING
                logger.info("Started playback")

    def _pause(self):
        """暂停"""
        if self._playback_status.state == PlaybackState.PLAYING:
            self._playback_status.state = PlaybackState.PAUSED
            logger.info("Paused playback")

    def _stop(self):
        """停止"""
        self._playback_status.state = PlaybackState.STOPPED
        self._playback_status.position = 0.0
        logger.info("Stopped playback")

    def _next(self):
        """下一首"""
        playlist = self._playback_status.playlist
        if not playlist or not playlist.songs:
            return

        current_index = self._playback_status.current_index
        next_index = current_index + 1

        if next_index >= len(playlist.songs):
            if self._playback_status.repeat_mode == RepeatMode.ALL:
                next_index = 0
            else:
                return

        self._playback_status.current_index = next_index
        self._playback_status.current_song = playlist.songs[next_index]
        self._playback_status.position = 0.0
        self._playback_status.state = PlaybackState.PLAYING
        logger.info("Next song: %s", self._playback_status.current_song.title)

    def _previous(self):
        """上一首"""
        playlist = self._playback_status.playlist
        if not playlist or not playlist.songs:
            return

        current_index = self._playback_status.current_index
        prev_index = current_index - 1

        if prev_index < 0:
            if self._playback_status.repeat_mode == RepeatMode.ALL:
                prev_index = len(playlist.songs) - 1
            else:
                return

        self._playback_status.current_index = prev_index
        self._playback_status.current_song = playlist.songs[prev_index]
        self._playback_status.position = 0.0
        self._playback_status.state = PlaybackState.PLAYING
        logger.info("Previous song: %s", self._playback_status.current_song.title)

    def _seek(self, position: float):
        """跳转到指定位置"""
        self._playback_status.position = max(0.0, position)
        logger.info("Seeked to %.1f seconds", position)

    def _set_volume(self, volume: float):
        """设置音量"""
        self._playback_status.volume = max(0.0, min(1.0, volume))
        self._playback_status.is_muted = False
        logger.info("Volume set to %.0f%%", volume * 100)

    def _toggle_mute(self):
        """切换静音"""
        self._playback_status.is_muted = not self._playback_status.is_muted
        logger.info("Mute: %s", self._playback_status.is_muted)

    def _set_repeat(self, mode: RepeatMode):
        """设置循环模式"""
        self._playback_status.repeat_mode = mode
        logger.info("Repeat mode: %s", mode.value)

    def _toggle_shuffle(self):
        """切换随机播放"""
        self._playback_status.is_shuffle = not self._playback_status.is_shuffle
        logger.info("Shuffle: %s", self._playback_status.is_shuffle)

    def _play_song(self, song_id: str):
        """播放指定歌曲"""
        song = self._songs.get(song_id)
        if not song:
            logger.error("Song not found: %s", song_id)
            return

        playlist = self._playback_status.playlist
        if playlist:
            for i, s in enumerate(playlist.songs):
                if s.id == song_id:
                    self._playback_status.current_index = i
                    break

        self._playback_status.current_song = song
        self._playback_status.position = 0.0
        self._playback_status.state = PlaybackState.PLAYING
        logger.info("Playing song: %s", song.title)

    def _play_playlist(self, playlist_id: str):
        """播放播放列表"""
        playlist = self._playlists.get(playlist_id)
        if not playlist or not playlist.songs:
            logger.error("Playlist not found or empty: %s", playlist_id)
            return

        self._playback_status.playlist = playlist
        self._playback_status.current_index = 0
        self._playback_status.current_song = playlist.songs[0]
        self._playback_status.position = 0.0
        self._playback_status.state = PlaybackState.PLAYING
        logger.info("Playing playlist: %s", playlist.name)

    def get_all_playlists(self) -> List[Playlist]:
        """获取所有播放列表"""
        return list(self._playlists.values())

    def get_dlna_devices(self) -> List[DLNADevice]:
        """获取DLNA设备列表"""
        devices = self._dlna_service.devices
        return [
            DLNADevice(
                id=d.udn,
                name=d.name,
                type=d.device_info.device_type,
                host=d.host,
                port=d.device_info.port,
                manufacturer=d.device_info.manufacturer,
                model=d.device_info.model_name,
                is_online=True,
            )
            for d in devices
        ]

    async def discover_dlna_devices(self, timeout: int = 5) -> List[DLNADevice]:
        """发现DLNA设备"""
        devices = await self._dlna_service.discover_devices(timeout)
        return [
            DLNADevice(
                id=d.udn,
                name=d.name,
                type=d.device_info.device_type,
                host=d.host,
                port=d.device_info.port,
                manufacturer=d.device_info.manufacturer,
                model=d.device_info.model_name,
                is_online=True,
            )
            for d in devices
        ]

    async def cast_to_dlna(self, request: DLNACastRequest) -> bool:
        """投屏到DLNA设备"""
        song = None
        if request.song_id:
            song = self._songs.get(request.song_id)
        elif self._playback_status.current_song:
            song = self._playback_status.current_song

        if not song:
            logger.error("No song to cast")
            return False

        # 构建完整的音频URL
        audio_url = song.audio_url
        if not audio_url.startswith("http"):
            # 需要构建完整的URL (实际部署时需要根据服务器地址构建)
            audio_url = f"http://localhost:8000{audio_url}"

        return await self._dlna_service.cast_to_device(
            request.device_id,
            audio_url,
        )

    async def stop_dlna_cast(self, device_id: str) -> bool:
        """停止DLNA投屏"""
        return await self._dlna_service.stop_cast(device_id)

    def scan_local_music(self, request: LocalMusicScanRequest) -> LocalMusicScanResult:
        """
        扫描本地音乐文件
        
        Args:
            request: 扫描请求，包含路径和是否递归
            
        Returns:
            扫描结果
        """
        scan_path = Path(request.path)
        errors = []
        scanned_songs = []
        
        # 支持的音频格式
        audio_extensions: Set[str] = {
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus', '.ape'
        }
        
        if not scan_path.exists():
            errors.append(f"路径不存在: {request.path}")
            return LocalMusicScanResult(
                songs=[],
                total=0,
                scan_path=request.path,
                errors=errors,
            )
        
        if not scan_path.is_dir():
            errors.append(f"路径不是目录: {request.path}")
            return LocalMusicScanResult(
                songs=[],
                total=0,
                scan_path=request.path,
                errors=errors,
            )
        
        try:
            # 获取音频文件列表
            if request.recursive:
                files = [f for f in scan_path.rglob('*') if f.is_file() and f.suffix.lower() in audio_extensions]
            else:
                files = [f for f in scan_path.iterdir() if f.is_file() and f.suffix.lower() in audio_extensions]
            
            for audio_file in files:
                try:
                    song = self._read_audio_metadata(audio_file)
                    if song:
                        # 检查是否已存在（基于文件路径）
                        existing = self._find_song_by_path(str(audio_file))
                        if existing:
                            scanned_songs.append(existing)
                        else:
                            self._songs[song.id] = song
                            scanned_songs.append(song)
                except Exception as e:
                    errors.append(f"读取文件失败 {audio_file.name}: {str(e)}")
                    logger.warning("Failed to read audio file %s: %s", audio_file, e)
            
            # 更新默认播放列表
            if scanned_songs:
                self._update_local_playlist(scanned_songs, request.path)
            
            logger.info("Scanned %d songs from %s", len(scanned_songs), request.path)

            # Persist scanned songs to disk
            if scanned_songs:
                self._save_persisted_songs()

        except PermissionError:
            errors.append(f"没有权限访问目录: {request.path}")
        except Exception as e:
            errors.append(f"扫描失败: {str(e)}")
            logger.error("Scan failed: %s", e)
        
        return LocalMusicScanResult(
            songs=scanned_songs,
            total=len(scanned_songs),
            scan_path=request.path,
            errors=errors,
        )

    def _read_audio_metadata(self, file_path: Path) -> Optional[Song]:
        """
        读取音频文件元数据
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            Song对象或None
        """
        try:
            # 尝试导入mutagen
            try:
                from mutagen import File
                from mutagen.id3 import ID3
                from mutagen.mp3 import MP3
                from mutagen.flac import FLAC
                from mutagen.mp4 import MP4
                from mutagen.oggvorbis import OggVorbis
                has_mutagen = True
            except ImportError:
                logger.warning("mutagen not available, using basic file info")
                has_mutagen = False
            
            if has_mutagen:
                audio = File(str(file_path), easy=True)
                if audio is None:
                    # 尝试使用基本方式读取
                    return self._create_song_from_file(file_path)
                
                # 提取元数据
                title = audio.get('title', [file_path.stem])[0] if audio.get('title') else file_path.stem
                artist = audio.get('artist', ['未知艺术家'])[0] if audio.get('artist') else '未知艺术家'
                album = audio.get('album', ['未知专辑'])[0] if audio.get('album') else '未知专辑'
                
                # 获取时长
                duration = 0.0
                if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                    duration = audio.info.length
                
                # 生成唯一ID（基于文件路径）
                song_id = f"local_{uuid.uuid5(uuid.NAMESPACE_URL, str(file_path))}"
                
                # 构建音频URL
                audio_url = f"/api/music/stream/{song_id}"
                
                # 提取封面并保存到磁盘
                cover_url = self._save_cover(file_path, song_id)

                # 提取歌词并保存到磁盘
                lyrics = self._extract_lyrics(file_path, audio)
                if lyrics:
                    self._save_lyrics(song_id, lyrics)
                    logger.info("Lyrics found for %s: %d lines", file_path.name, len(lyrics))
                else:
                    logger.debug("No lyrics for %s", file_path.name)

                song = Song(
                    id=song_id,
                    title=title,
                    artist=artist,
                    album=album,
                    duration=duration,
                    cover_url=cover_url,
                    audio_url=audio_url,
                    lyrics=lyrics or [],
                )
                
                # 保存文件路径映射
                if not hasattr(self, '_file_path_map'):
                    self._file_path_map = {}
                self._file_path_map[song_id] = str(file_path)
                
                return song
            else:
                # 没有mutagen，使用基本文件信息
                return self._create_song_from_file(file_path)
            
        except Exception as e:
            logger.warning("Failed to read metadata for %s: %s", file_path, e)
            return self._create_song_from_file(file_path)

    def _create_song_from_file(self, file_path: Path) -> Song:
        """从文件创建基本Song对象（无元数据时）"""
        song_id = f"local_{uuid.uuid5(uuid.NAMESPACE_URL, str(file_path))}"
        audio_url = f"/api/music/stream/{song_id}"

        if not hasattr(self, '_file_path_map'):
            self._file_path_map = {}
        self._file_path_map[song_id] = str(file_path)

        cover_url = self._save_cover(file_path, song_id)

        return Song(
            id=song_id,
            title=file_path.stem,
            artist='未知艺术家',
            album='未知专辑',
            duration=0.0,
            cover_url=cover_url,
            audio_url=audio_url,
            lyrics=None,
        )

    def extract_cover_bytes(self, file_path: Path) -> tuple:
        """
        Extract cover art as raw bytes.
        Priority: embedded tags > external image files in same directory.
        Returns (bytes, mime_type) or (None, None).
        """
        # ── 1. Try embedded cover art ──
        try:
            suffix = file_path.suffix.lower()

            if suffix == '.mp3':
                from mutagen.id3 import ID3
                tags = ID3(str(file_path))
                for tag in tags.values():
                    if tag.FrameID == 'APIC':
                        return (tag.data, tag.mime)

            elif suffix == '.flac':
                from mutagen.flac import FLAC
                flac = FLAC(str(file_path))
                if flac.pictures:
                    return (flac.pictures[0].data, flac.pictures[0].mime)

            elif suffix in ['.m4a', '.mp4']:
                from mutagen.mp4 import MP4
                mp4 = MP4(str(file_path))
                if 'covr' in mp4:
                    return (bytes(mp4['covr'][0]), 'image/jpeg')

            elif suffix in ['.ogg', '.opus']:
                from mutagen import File as MutagenFile
                from mutagen.flac import Picture
                from base64 import b64decode
                audio = MutagenFile(str(file_path))
                if audio and 'metadata_block_picture' in audio:
                    for block in audio['metadata_block_picture']:
                        pic = Picture(b64decode(block))
                        return (pic.data, pic.mime)

        except Exception as e:
            logger.debug("Embedded cover extraction failed for %s: %s", file_path.name, e)

        # ── 2. Try external cover files in same directory ──
        cover_names = [
            'cover.jpg', 'cover.jpeg', 'cover.png',
            'folder.jpg', 'folder.jpeg', 'folder.png',
            'front.jpg', 'front.jpeg', 'front.png',
            'album.jpg', 'album.jpeg', 'album.png',
            'Cover.jpg', 'Cover.JPG', 'Folder.jpg',
        ]
        parent = file_path.parent
        for name in cover_names:
            cover_path = parent / name
            if cover_path.exists():
                try:
                    mime = 'image/jpeg' if cover_path.suffix.lower() in ['.jpg', '.jpeg'] else 'image/png'
                    return (cover_path.read_bytes(), mime)
                except Exception as e:
                    logger.debug("Failed to read cover file %s: %s", cover_path, e)

        return (None, None)

    def _save_cover(self, file_path: Path, song_id: str) -> Optional[str]:
        """
        提取封面并保存到磁盘，返回封面 URL。
        优先级：内嵌封面 > 目录下图片文件。
        """
        cover_bytes, mime = self.extract_cover_bytes(file_path)
        if not cover_bytes:
            return None

        # 确定文件扩展名
        ext = '.jpg'
        if mime and 'png' in mime:
            ext = '.png'
        elif mime and 'webp' in mime:
            ext = '.webp'

        cover_filename = f"{song_id}{ext}"
        cover_path = self._covers_dir / cover_filename

        try:
            cover_path.write_bytes(cover_bytes)
            logger.debug("Saved cover for %s: %s", song_id, cover_path)
            return f"/api/music/cover/{song_id}"
        except Exception as e:
            logger.warning("Failed to save cover for %s: %s", song_id, e)

    def _save_lyrics(self, song_id: str, lyrics: List[LyricLine]) -> bool:
        """Save lyrics to disk as JSON."""
        lyrics_path = self._lyrics_dir / f"{song_id}.json"
        try:
            import json
            data = [{"time": l.time, "text": l.text} for l in lyrics]
            lyrics_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            logger.warning("Failed to save lyrics for %s: %s", song_id, e)
            return False

    def get_lyrics_from_disk(self, song_id: str) -> Optional[List[LyricLine]]:
        """Load lyrics from disk."""
        lyrics_path = self._lyrics_dir / f"{song_id}.json"
        if not lyrics_path.exists():
            return None
        try:
            import json
            data = json.loads(lyrics_path.read_text(encoding="utf-8"))
            return [LyricLine(time=l["time"], text=l["text"]) for l in data]
        except Exception as e:
            logger.debug("Failed to load lyrics for %s: %s", song_id, e)
            return None
            return None

    def _extract_lyrics(self, file_path: Path, audio) -> Optional[List[LyricLine]]:
        """
        Extract lyrics from audio file.
        Priority: external .lrc file > embedded lyrics tag.
        """
        # ── 1. Try external .lrc file (same name as audio) ──
        lrc_path = file_path.with_suffix('.lrc')
        if lrc_path.exists():
            try:
                lrc_text = lrc_path.read_text(encoding='utf-8')
                parsed = self._parse_lrc(lrc_text)
                if parsed:
                    return parsed
            except Exception as e:
                logger.debug("Failed to read .lrc file %s: %s", lrc_path, e)
            # Try other encodings
            for enc in ['gbk', 'gb2312', 'big5', 'latin-1']:
                try:
                    lrc_text = lrc_path.read_text(encoding=enc)
                    parsed = self._parse_lrc(lrc_text)
                    if parsed:
                        return parsed
                except Exception:
                    continue

        # ── 2. Try embedded lyrics ──
        try:
            suffix = file_path.suffix.lower()

            # MP3: ID3 USLT (Unsynchronized Lyrics) frame
            if suffix == '.mp3':
                from mutagen.id3 import ID3
                tags = ID3(str(file_path))
                for key in tags:
                    if key.startswith('USLT'):
                        text = tags[key].text
                        if text:
                            parsed = self._parse_lrc(text)
                            if parsed:
                                return parsed
                            # Plain text lyrics (no timestamps)
                            lines = [l.strip() for l in text.split('\n') if l.strip()]
                            if lines:
                                return [LyricLine(time=0.0, text="")] + [
                                    LyricLine(time=5.0 + i * 5.0, text=l)
                                    for i, l in enumerate(lines)
                                ]
                # Also check SYLT (Synchronized Lyrics)
                for key in tags:
                    if key.startswith('SYLT'):
                        lyrics_data = tags[key]
                        if lyrics_data.text:
                            lines = []
                            for item in lyrics_data.text:
                                if isinstance(item, tuple) and len(item) >= 2:
                                    text, time_ms = item[0], item[1]
                                    lines.append(LyricLine(time=time_ms / 1000.0, text=text.strip()))
                            if lines:
                                return sorted(lines, key=lambda l: l.time)

            # FLAC: LYRICS tag
            elif suffix == '.flac':
                from mutagen.flac import FLAC
                flac = FLAC(str(file_path))
                if 'LYRICS' in flac:
                    text = flac['LYRICS'][0]
                    if text:
                        parsed = self._parse_lrc(text)
                        if parsed:
                            return parsed
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        if lines:
                            return [LyricLine(time=0.0, text="")] + [
                                LyricLine(time=5.0 + i * 5.0, text=l)
                                for i, l in enumerate(lines)
                            ]

            # M4A/MP4: ©lyr tag
            elif suffix in ['.m4a', '.mp4']:
                from mutagen.mp4 import MP4
                mp4 = MP4(str(file_path))
                if '©lyr' in mp4:
                    text = mp4['©lyr'][0]
                    if text:
                        parsed = self._parse_lrc(text)
                        if parsed:
                            return parsed
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        if lines:
                            return [LyricLine(time=0.0, text="")] + [
                                LyricLine(time=5.0 + i * 5.0, text=l)
                                for i, l in enumerate(lines)
                            ]

            # OGG: LYRICS tag
            elif suffix == '.ogg':
                from mutagen.oggvorbis import OggVorbis
                ogg = OggVorbis(str(file_path))
                if 'LYRICS' in ogg:
                    text = ogg['LYRICS'][0]
                    if text:
                        parsed = self._parse_lrc(text)
                        if parsed:
                            return parsed

        except Exception as e:
            logger.warning("Failed to extract lyrics from %s: %s", file_path, e)

        return None

    @staticmethod
    def _parse_lrc(text: str) -> Optional[List[LyricLine]]:
        """Parse LRC format lyrics into sorted LyricLine list."""
        import re
        if not text:
            return None
        lines = text.split('\n')
        result = []
        time_re = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
        for line in lines:
            matches = time_re.findall(line)
            if not matches:
                continue
            lyric_text = time_re.sub('', line).strip()
            if not lyric_text:
                continue
            for m in matches:
                mins, secs, ms = int(m[0]), int(m[1]), int(m[2].ljust(3, '0')) if m[2] else 0
                t = mins * 60 + secs + ms / 1000.0
                result.append(LyricLine(time=t, text=lyric_text))
        return sorted(result, key=lambda l: l.time) if result else None

    def _find_song_by_path(self, file_path: str) -> Optional[Song]:
        """根据文件路径查找已存在的歌曲"""
        if not hasattr(self, '_file_path_map'):
            return None
        
        for song_id, path in self._file_path_map.items():
            if path == file_path:
                return self._songs.get(song_id)
        return None

    def _update_local_playlist(self, songs: List[Song], scan_path: str):
        """更新本地音乐播放列表"""
        playlist_id = "playlist_local"
        playlist_name = f"本地音乐 - {Path(scan_path).name}"
        
        if playlist_id in self._playlists:
            # 合并歌曲，避免重复
            existing_ids = {s.id for s in self._playlists[playlist_id].songs}
            new_songs = [s for s in songs if s.id not in existing_ids]
            self._playlists[playlist_id].songs.extend(new_songs)
        else:
            # 创建新播放列表
            playlist = Playlist(
                id=playlist_id,
                name=playlist_name,
                songs=songs,
            )
            self._playlists[playlist_id] = playlist

    def get_audio_file_path(self, song_id: str) -> Optional[str]:
        """获取音频文件的实际路径"""
        if not hasattr(self, '_file_path_map'):
            return None
        return self._file_path_map.get(song_id)


def get_music_service() -> MusicService:
    """获取音乐服务单例"""
    global _music_service_instance
    if _music_service_instance is None:
        _music_service_instance = MusicService()
    return _music_service_instance


def set_music_service(service: MusicService):
    """设置音乐服务单例"""
    global _music_service_instance
    _music_service_instance = service
