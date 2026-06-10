import React, { useState, useEffect } from 'react'
import { message } from 'antd'
import { useMusicPlayerStore } from '@/stores/musicPlayerStore'
import styles from './index.module.less'

// ─── Icons ─────────────────────────────────────────

const FolderIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
  </svg>
)

const ScanIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="11" cy="11" r="8" />
    <path d="M21 21l-4.35-4.35" />
  </svg>
)

const PlusIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
)

const TrashIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
  </svg>
)

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#52c41a" strokeWidth="2">
    <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
)

const WarnIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#faad14" strokeWidth="2">
    <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
)

// ─── Component ─────────────────────────────────────

const MusicSettings = () => {
  const {
    scanLoading, scanResult, scanError,
    scanLocalMusicPath, clearScanResults,
    scanDirs, loadScanDirs, addScanDir, removeScanDir,
    loadPlaylistFromBackend,
  } = useMusicPlayerStore()

  // Quick scan
  const [scanPath, setScanPath] = useState('')
  const [recursive, setRecursive] = useState(true)

  // Add directory
  const [showAddDir, setShowAddDir] = useState(false)
  const [newDirPath, setNewDirPath] = useState('')
  const [newDirName, setNewDirName] = useState('')
  const [newDirRecursive, setNewDirRecursive] = useState(true)

  useEffect(() => {
    loadScanDirs()
    return () => clearScanResults()
  }, [loadScanDirs, clearScanResults])

  // ─── Quick Scan ─────────────────────────────────

  const handleScan = async () => {
    if (!scanPath.trim()) {
      message.warning('请输入扫描路径')
      return
    }
    clearScanResults()
    await scanLocalMusicPath(scanPath.trim(), recursive)
    // Reload playlist from backend to pick up new songs
    await loadPlaylistFromBackend()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleScan()
  }

  // ─── Directory Management ───────────────────────

  const handleAddDir = async () => {
    if (!newDirPath.trim()) {
      message.warning('请输入目录路径')
      return
    }
    const ok = await addScanDir({
      path: newDirPath.trim(),
      name: newDirName.trim() || newDirPath.trim().split(/[/\\]/).pop() || '未命名',
      recursive: newDirRecursive,
    })
    if (ok) {
      setShowAddDir(false)
      setNewDirPath('')
      setNewDirName('')
      setNewDirRecursive(true)
      message.success('目录已添加')
    }
  }

  const handleRemoveDir = async (dirId) => {
    await removeScanDir(dirId)
  }

  const handleScanSavedDir = async (dir) => {
    clearScanResults()
    await scanLocalMusicPath(dir.path, dir.recursive)
    await loadPlaylistFromBackend()
  }

  return (
    <div className={styles.container}>
      {/* ── Section: Scan Directories ────────────── */}
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>扫描目录</h3>
        <button
          className={styles.addBtn}
          onClick={() => setShowAddDir(!showAddDir)}
        >
          <PlusIcon />
          <span>添加</span>
        </button>
      </div>

      {/* Add Directory Form */}
      {showAddDir && (
        <div className={styles.addForm}>
          <div className={styles.formRow}>
            <div className={styles.formInput}>
              <FolderIcon />
              <input
                type="text"
                placeholder="目录路径，如 D:\Music"
                value={newDirPath}
                onChange={(e) => setNewDirPath(e.target.value)}
              />
            </div>
          </div>
          <div className={styles.formRow}>
            <input
              type="text"
              placeholder="名称（可选）"
              value={newDirName}
              onChange={(e) => setNewDirName(e.target.value)}
              className={styles.formInputSmall}
            />
            <label
              className={styles.toggle}
              onClick={() => setNewDirRecursive(!newDirRecursive)}
            >
              <span className={`${styles.checkbox} ${newDirRecursive ? styles.checked : ''}`}>
                {newDirRecursive && (
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </span>
              <span className={styles.toggleLabel}>递归</span>
            </label>
            <button className={styles.confirmBtn} onClick={handleAddDir}>
              添加
            </button>
          </div>
        </div>
      )}

      {/* Directory List */}
      {scanDirs.length > 0 ? (
        <div className={styles.dirList}>
          {scanDirs.map((dir) => (
            <div key={dir.id} className={styles.dirItem}>
              <div className={styles.dirInfo}>
                <div className={styles.dirIcon}>
                  <FolderIcon />
                </div>
                <div className={styles.dirMeta}>
                  <span className={styles.dirName}>{dir.name || dir.path}</span>
                  <span className={styles.dirPath}>{dir.path}</span>
                </div>
                {dir.recursive && <span className={styles.dirTag}>递归</span>}
              </div>
              <div className={styles.dirActions}>
                <button
                  className={styles.dirActionBtn}
                  title="扫描"
                  onClick={() => handleScanSavedDir(dir)}
                  disabled={scanLoading}
                >
                  <ScanIcon />
                </button>
                <button
                  className={styles.dirActionBtnDanger}
                  title="删除"
                  onClick={() => handleRemoveDir(dir.id)}
                >
                  <TrashIcon />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : !showAddDir ? (
        <div className={styles.empty}>
          <p>暂无保存的目录</p>
        </div>
      ) : null}

      {/* ── Divider ─────────────────────────────── */}
      <div className={styles.divider} />

      {/* ── Section: Quick Scan ─────────────────── */}
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>快速扫描</h3>
      </div>

      <div className={styles.inputRow}>
        <div className={styles.pathInput}>
          <FolderIcon />
          <input
            type="text"
            placeholder="输入音乐目录路径，如 D:\Music"
            value={scanPath}
            onChange={(e) => setScanPath(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={scanLoading}
          />
        </div>
      </div>

      <div className={styles.optionsRow}>
        <label
          className={styles.toggle}
          onClick={() => !scanLoading && setRecursive(!recursive)}
        >
          <span className={`${styles.checkbox} ${recursive ? styles.checked : ''}`}>
            {recursive && (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
          </span>
          <span className={styles.toggleLabel}>递归扫描子目录</span>
        </label>
        <button
          className={styles.scanBtn}
          onClick={handleScan}
          disabled={scanLoading || !scanPath.trim()}
        >
          {scanLoading ? <span className={styles.spinner} /> : <ScanIcon />}
          <span>{scanLoading ? '扫描中...' : '开始扫描'}</span>
        </button>
      </div>

      <div className={styles.hint}>
        支持: MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS, APE
      </div>

      {/* Progress */}
      {scanLoading && (
        <div className={styles.progress}>
          <div className={styles.progressBar}>
            <div className={styles.progressFill} />
          </div>
          <span className={styles.progressText}>正在扫描...</span>
        </div>
      )}

      {/* Error */}
      {scanError && (
        <div className={styles.alertWarn}>
          <WarnIcon />
          <span>{scanError}</span>
        </div>
      )}

      {/* Result */}
      {scanResult && (
        <div className={styles.result}>
          <CheckIcon />
          <span>扫描完成 — 共 {scanResult.total || 0} 首，新增 {scanResult.new_count || 0} 首</span>
        </div>
      )}
    </div>
  )
}

export default MusicSettings
