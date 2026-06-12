# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Music Schema - Data models for music player module.
音乐数据模型 - 定义音乐播放器相关的数据结构
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PlaybackState(str, Enum):
    """播放状态枚举"""
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    LOADING = "loading"
    ERROR = "error"


class RepeatMode(str, Enum):
    """循环模式枚举"""
    OFF = "off"
    ALL = "all"
    ONE = "one"


class LyricLine(BaseModel):
    """歌词行模型"""
    time: float = Field(..., description="歌词时间点(秒)")
    text: str = Field(..., description="歌词文本")


class Song(BaseModel):
    """歌曲模型"""
    id: str = Field(..., description="歌曲唯一ID")
    title: str = Field(..., description="歌曲标题")
    artist: str = Field(default="未知艺术家", description="艺术家名称")
    album: str = Field(default="未知专辑", description="专辑名称")
    duration: float = Field(default=0.0, description="歌曲时长(秒)")
    cover_url: Optional[str] = Field(None, description="封面图URL")
    audio_url: str = Field(..., description="音频文件URL")
    lyrics: Optional[List[LyricLine]] = Field(None, description="歌词数据")


class Playlist(BaseModel):
    """播放列表模型"""
    id: str = Field(..., description="播放列表唯一ID")
    name: str = Field(..., description="播放列表名称")
    songs: List[Song] = Field(default_factory=list, description="歌曲列表")
    cover_url: Optional[str] = Field(None, description="播放列表封面URL")


class DLNADevice(BaseModel):
    """DLNA设备模型"""
    id: str = Field(..., description="设备唯一标识")
    name: str = Field(..., description="设备名称")
    type: str = Field(default="speaker", description="设备类型")
    host: str = Field(..., description="设备IP地址")
    port: int = Field(default=0, description="设备端口")
    manufacturer: Optional[str] = Field(None, description="制造商")
    model: Optional[str] = Field(None, description="型号")
    is_online: bool = Field(default=True, description="是否在线")


class PlaybackStatus(BaseModel):
    """播放状态模型"""
    state: PlaybackState = Field(default=PlaybackState.STOPPED, description="播放状态")
    current_song: Optional[Song] = Field(None, description="当前播放歌曲")
    current_index: int = Field(default=0, description="当前歌曲索引")
    position: float = Field(default=0.0, description="当前播放位置(秒)")
    volume: float = Field(default=0.7, description="音量(0-1)")
    is_muted: bool = Field(default=False, description="是否静音")
    repeat_mode: RepeatMode = Field(default=RepeatMode.OFF, description="循环模式")
    is_shuffle: bool = Field(default=False, description="是否随机播放")
    playlist: Optional[Playlist] = Field(None, description="当前播放列表")
    dlna_device: Optional[DLNADevice] = Field(None, description="当前DLNA投屏设备")


class MusicControlAction(str, Enum):
    """音乐控制操作枚举"""
    PLAY = "play"
    PAUSE = "pause"
    STOP = "stop"
    NEXT = "next"
    PREVIOUS = "previous"
    SEEK = "seek"
    SET_VOLUME = "set_volume"
    TOGGLE_MUTE = "toggle_mute"
    SET_REPEAT = "set_repeat"
    TOGGLE_SHUFFLE = "toggle_shuffle"
    PLAY_SONG = "play_song"
    PLAY_PLAYLIST = "play_playlist"
    CAST_TO_DLNLA = "cast_to_dlna"
    STOP_CAST = "stop_cast"


class MusicControlRequest(BaseModel):
    """音乐控制请求模型"""
    action: MusicControlAction = Field(..., description="控制操作")
    song_id: Optional[str] = Field(None, description="歌曲ID(播放指定歌曲时)")
    playlist_id: Optional[str] = Field(None, description="播放列表ID")
    position: Optional[float] = Field(None, description="跳转位置(秒)")
    volume: Optional[float] = Field(None, description="音量值(0-1)")
    repeat_mode: Optional[RepeatMode] = Field(None, description="循环模式")
    dlna_device_id: Optional[str] = Field(None, description="DLNA设备ID")


class MusicSearchRequest(BaseModel):
    """音乐搜索请求模型"""
    keyword: str = Field(..., description="搜索关键词")
    search_type: str = Field(default="song", description="搜索类型: song/artist/album")


class MusicSearchResult(BaseModel):
    """音乐搜索结果模型"""
    songs: List[Song] = Field(default_factory=list, description="歌曲结果")
    total: int = Field(default=0, description="结果总数")


class DLNADiscoverRequest(BaseModel):
    """DLNA设备发现请求模型"""
    timeout: int = Field(default=5, description="发现超时时间(秒)")


class DLNACastRequest(BaseModel):
    """DLNA投屏请求模型"""
    device_id: str = Field(..., description="目标设备ID")
    song_id: Optional[str] = Field(None, description="要投屏的歌曲ID")
    audio_url: Optional[str] = Field(None, description="音频URL（在线歌曲直接传入）")


class LocalMusicScanRequest(BaseModel):
    """本地音乐扫描请求模型"""
    path: str = Field(..., description="扫描路径(绝对路径)")
    recursive: bool = Field(default=True, description="是否递归扫描子目录")


class LocalMusicScanResult(BaseModel):
    """本地音乐扫描结果模型"""
    songs: List[Song] = Field(default_factory=list, description="扫描到的歌曲列表")
    total: int = Field(default=0, description="歌曲总数")
    scan_path: str = Field(..., description="扫描路径")
    errors: List[str] = Field(default_factory=list, description="扫描过程中的错误")
