import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Tablet, HardDrive, FolderOpen, CheckCircle, RefreshCw,
  ArrowLeft, Download, Search, Info, Plus, Archive, Clock
} from 'lucide-react';
import StatusCard from './components/StatusCard';
import ProgressBar from './components/ProgressBar';
import { useBackend, useDirectoryPicker } from './hooks/useBackend';

function formatSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '0s';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function useTimer(running) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(null);

  useEffect(() => {
    if (running) {
      startRef.current = Date.now();
      setElapsed(0);
      const id = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
      }, 1000);
      return () => clearInterval(id);
    }
  }, [running]);

  return elapsed;
}

// ─── Mode selection (entry point) ───
const MODE = { CHOOSE: 'choose', BACKUP: 'backup', EXTRACT: 'extract' };
// ─── Steps within extract mode ───
const STEP = { PASSWORD: 0, SCAN: 1, EXPORT: 2, DONE: 3 };

export default function App() {
  const { callBackend, progress, clearProgress } = useBackend();
  const { pickDirectory } = useDirectoryPicker();

  const [mode, setMode] = useState(MODE.CHOOSE);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Backup mode state
  const [device, setDevice] = useState(null);
  const [backupDir, setBackupDir] = useState('');
  const [backupDirSpace, setBackupDirSpace] = useState(null);
  const [backupDone, setBackupDone] = useState(false);
  const [backupInfo, setBackupInfo] = useState(null);

  // Extract mode state
  const [step, setStep] = useState(STEP.PASSWORD);
  const [backupPath, setBackupPath] = useState('');
  const [password, setPassword] = useState('');
  const [passwordValid, setPasswordValid] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [exportDir, setExportDir] = useState('');
  const [exportDirSpace, setExportDirSpace] = useState(null);
  const [exportResult, setExportResult] = useState(null);

  // Live timer for export progress
  const timerElapsed = useTimer(step === STEP.EXPORT);

  // ─── Backup mode handlers ───

  const detectDevice = async () => {
    for (let i = 0; i < 3; i++) {
      const result = await callBackend('detect_device');
      if (result?.found) { setDevice(result); return; }
      if (i < 2) await new Promise(r => setTimeout(r, 2000));
    }
    setDevice(await callBackend('detect_device'));
  };

  const handleSelectBackupDir = async () => {
    const dir = await pickDirectory();
    if (dir) {
      setBackupDir(dir);
      const space = await callBackend('get_disk_space', { path: dir });
      setBackupDirSpace(space);
    }
  };

  const handleStartBackup = async () => {
    if (!backupDir) { setError('Please select backup directory'); return; }
    setError(null);
    setBusy(true);
    clearProgress();

    const result = await callBackend('create_backup', { backup_dir: backupDir });
    if (result?.error) {
      setError(result.error);
    } else {
      setBackupDone(true);
      setBackupInfo(result);
    }
    setBusy(false);
  };

  // ─── Extract mode handlers ───

  const handleSelectBackupPath = async () => {
    const dir = await pickDirectory();
    if (dir) {
      setBackupPath(dir);
      setPasswordValid(null);
    }
  };

  const handleSelectExportDir = async () => {
    const dir = await pickDirectory();
    if (dir) {
      setExportDir(dir);
      const space = await callBackend('get_disk_space', { path: dir });
      setExportDirSpace(space);
    }
  };

  const handleValidateAndScan = async () => {
    if (!backupPath) { setError('Please select backup folder'); return; }
    if (!password) { setError('Please enter password'); return; }
    setError(null);
    setBusy(true);
    clearProgress();

    // Validate password
    const pwResult = await callBackend('validate_password', {
      backup_path: backupPath,
      password: password,
    });
    if (!pwResult?.valid) {
      setError(pwResult?.error || 'Password validation failed');
      setPasswordValid(false);
      setBusy(false);
      return;
    }
    setPasswordValid(true);

    // Use the resolved backup path (auto-detected UDID subfolder)
    const resolvedPath = pwResult.backup_path || backupPath;
    setBackupPath(resolvedPath);

    // Scan
    const scan = await callBackend('scan_media', {
      backup_path: resolvedPath,
      password: password,
    });
    if (scan?.error) {
      setError(scan.error);
      setBusy(false);
      return;
    }
    setScanResult(scan);
    setStep(STEP.SCAN);
    setBusy(false);
  };

  const handleStartExport = async () => {
    if (!exportDir) { setError('Please select export directory'); return; }
    setError(null);
    setBusy(true);
    clearProgress();
    setStep(STEP.EXPORT);

    try {
      const result = await callBackend('export_media', {
        backup_path: backupPath,
        password: password,
        export_dir: exportDir + '/GoPro',
        organize_by_date: true,
        skip_duplicates: true,
      });
      if (result?.error) {
        setError(result.error);
        setStep(STEP.SCAN);
      } else {
        setExportResult(result);
        setStep(STEP.DONE);
      }
    } catch (err) {
      setError(err.message || 'Export failed');
      setStep(STEP.SCAN);
    }
    setBusy(false);
  };

  const handleReset = () => {
    setMode(MODE.CHOOSE);
    setStep(STEP.PASSWORD);
    setError(null);
    setBusy(false);
    setBackupPath('');
    setPassword('');
    setPasswordValid(null);
    setScanResult(null);
    setExportDir('');
    setExportDirSpace(null);
    setExportResult(null);
    setBackupDone(false);
    setBackupInfo(null);
    setBackupDir('');
    clearProgress();
  };

  // After backup completes, switch to extract mode with the backup path pre-filled
  const handleBackupToExtract = () => {
    setBackupPath(backupInfo.path);
    setMode(MODE.EXTRACT);
    setStep(STEP.PASSWORD);
    setError(null);
  };

  // ─── Render ───

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      {/* Title bar */}
      <div className="titlebar-drag h-12 flex items-center justify-between px-20 bg-white/80 backdrop-blur border-b border-slate-200">
        <h1 className="text-sm font-semibold text-slate-700">GoPro Extractor</h1>
        {mode !== MODE.CHOOSE && (
          <button onClick={handleReset}
            className="titlebar-no-drag text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1">
            <ArrowLeft size={12} /> Home
          </button>
        )}
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">

        {/* ════════ MODE CHOOSE ════════ */}
        {mode === MODE.CHOOSE && (
          <>
            <div className="text-center pt-8 pb-4">
              <h2 className="text-lg font-semibold text-slate-800">What would you like to do?</h2>
              <p className="text-sm text-slate-500 mt-1">Choose an option to get started</p>
            </div>

            <button onClick={() => { setMode(MODE.BACKUP); detectDevice(); }}
              className="w-full rounded-xl border-2 border-slate-200 bg-white p-5 hover:border-blue-400 hover:bg-blue-50/30 transition-colors text-left group">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center group-hover:bg-blue-200 transition-colors">
                  <Plus size={20} className="text-blue-600" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-800">Create iPad Backup</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    Connect iPad via USB and create an encrypted backup
                  </div>
                </div>
              </div>
            </button>

            <button onClick={() => setMode(MODE.EXTRACT)}
              className="w-full rounded-xl border-2 border-slate-200 bg-white p-5 hover:border-emerald-400 hover:bg-emerald-50/30 transition-colors text-left group">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center group-hover:bg-emerald-200 transition-colors">
                  <Archive size={20} className="text-emerald-600" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-800">Extract from Existing Backup</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    Select a backup folder and extract GoPro media
                  </div>
                </div>
              </div>
            </button>
          </>
        )}

        {/* ════════ MODE: BACKUP ════════ */}
        {mode === MODE.BACKUP && !backupDone && (
          <>
            <StatusCard
              icon={Tablet}
              title={device?.found ? device.name : 'iPad Not Connected'}
              subtitle={device?.found ? `iOS ${device.ios_version}` : 'Connect your iPad via USB'}
              status={device?.found ? 'connected' : 'disconnected'}
            >
              {!device?.found && (
                <button onClick={detectDevice}
                  className="mt-2 text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1">
                  <RefreshCw size={12} /> Retry
                </button>
              )}
            </StatusCard>

            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Save Backup To
              </label>
              <div className="flex items-center gap-2">
                <button onClick={handleSelectBackupDir} disabled={busy}
                  className="px-3 py-2 text-sm rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center gap-1.5 disabled:opacity-50">
                  <FolderOpen size={14} /> {backupDir ? 'Change' : 'Select folder'}
                </button>
                {backupDir && <span className="text-sm text-slate-600 truncate flex-1">{backupDir}</span>}
              </div>
              {backupDirSpace && (
                <p className="text-xs text-slate-400 mt-2">
                  Available: {formatSize(backupDirSpace.free)}
                  {backupDirSpace.free < 500 * 1024 * 1024 * 1024 && (
                    <span className="text-amber-500 ml-1">(iPad backup may need 200-500 GB)</span>
                  )}
                </p>
              )}
            </div>

            {busy && progress && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <h3 className="text-sm font-medium text-blue-800 mb-2">Creating backup...</h3>
                <ProgressBar percent={progress.percent} message={progress.message} />
              </div>
            )}
          </>
        )}

        {/* Backup complete */}
        {mode === MODE.BACKUP && backupDone && backupInfo && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle size={18} className="text-emerald-500" />
              <h3 className="text-sm font-semibold text-emerald-800">Backup Complete!</h3>
            </div>
            <div className="text-xs text-emerald-700 space-y-1">
              <p>Path: <span className="font-mono">{backupInfo.path}</span></p>
              <p>Size: {formatSize(backupInfo.size_bytes)}</p>
            </div>
          </div>
        )}

        {/* ════════ MODE: EXTRACT ════════ */}
        {mode === MODE.EXTRACT && (
          <>
            {/* Step 0: Select backup + password */}
            {step === STEP.PASSWORD && (
              <>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Backup Folder
                  </label>
                  <div className="flex items-center gap-2">
                    <button onClick={handleSelectBackupPath} disabled={busy}
                      className="px-3 py-2 text-sm rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center gap-1.5 disabled:opacity-50">
                      <FolderOpen size={14} /> {backupPath ? 'Change' : 'Select backup folder'}
                    </button>
                    {backupPath && <span className="text-sm text-slate-600 truncate flex-1">{backupPath}</span>}
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    Select the folder containing Manifest.db (usually named with device UDID)
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Backup Password
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => { setPassword(e.target.value); setPasswordValid(null); setError(null); }}
                    placeholder="Enter backup encryption password"
                    disabled={busy}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none disabled:bg-slate-100"
                  />
                  {passwordValid === false && (
                    <p className="text-xs text-red-500 mt-1">Password incorrect</p>
                  )}
                </div>

                {busy && (
                  <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                    <h3 className="text-sm font-medium text-blue-800 mb-2">Validating & scanning...</h3>
                    <ProgressBar percent={progress?.percent} message={progress?.message || 'Decrypting Manifest.db...'} />
                  </div>
                )}
              </>
            )}

            {/* Step 1: Scan results + export dir selection */}
            {step === STEP.SCAN && scanResult && (
              <>
                <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3">
                  <div className="flex items-center gap-2">
                    <Info size={14} className="text-blue-500" />
                    <span className="text-xs text-blue-700">iPad can be disconnected — only the backup files are needed now.</span>
                  </div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <h3 className="text-sm font-medium text-slate-700 mb-3">GoPro Media Found</h3>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="text-center p-3 rounded-lg bg-slate-50">
                      <div className="text-2xl font-bold text-slate-800">{scanResult.videos}</div>
                      <div className="text-xs text-slate-500">Videos</div>
                    </div>
                    <div className="text-center p-3 rounded-lg bg-slate-50">
                      <div className="text-2xl font-bold text-slate-800">{scanResult.photos}</div>
                      <div className="text-xs text-slate-500">Photos</div>
                    </div>
                    <div className="text-center p-3 rounded-lg bg-slate-50">
                      <div className="text-2xl font-bold text-slate-800">{scanResult.total}</div>
                      <div className="text-xs text-slate-500">Total</div>
                    </div>
                  </div>
                  {scanResult.total === 0 && (
                    <p className="text-sm text-amber-600 mt-3">No GoPro media found in this backup.</p>
                  )}
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <label className="block text-sm font-medium text-slate-700 mb-2">Export To</label>
                  <div className="flex items-center gap-2">
                    <button onClick={handleSelectExportDir}
                      className="px-3 py-2 text-sm rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center gap-1.5">
                      <FolderOpen size={14} /> {exportDir ? 'Change' : 'Select folder'}
                    </button>
                    {exportDir && <span className="text-sm text-slate-600 truncate flex-1">{exportDir}</span>}
                  </div>
                  {exportDir && (
                    <p className="text-xs text-slate-400 mt-2">
                      Export to: <span className="font-mono">{exportDir}/GoPro/YYYY/MM/</span>
                    </p>
                  )}
                  {exportDirSpace && (
                    <p className="text-xs text-slate-400 mt-1">Available: {formatSize(exportDirSpace.free)}</p>
                  )}
                </div>
              </>
            )}

            {/* Step 2: Exporting progress */}
            {step === STEP.EXPORT && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-medium text-blue-800">
                    {progress?.stage === 'dedup' ? 'Checking duplicates...' : 'Exporting GoPro media...'}
                  </h3>
                  <span className="text-xs text-blue-600 flex items-center gap-1">
                    <Clock size={12} /> {formatDuration(timerElapsed)}
                  </span>
                </div>
                {progress && <ProgressBar percent={progress.percent} message={progress.message} />}
              </div>
            )}

            {/* Step 3: Done */}
            {step === STEP.DONE && exportResult && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle size={20} className="text-emerald-500" />
                  <h3 className="text-sm font-semibold text-emerald-800">Export Complete!</h3>
                </div>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div className="p-2 rounded-lg bg-white/60">
                    <div className="text-lg font-bold text-slate-800">{exportResult.exported}</div>
                    <div className="text-xs text-slate-500">Files exported</div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/60">
                    <div className="text-lg font-bold text-slate-800">{formatSize(exportResult.total_bytes)}</div>
                    <div className="text-xs text-slate-500">Total size</div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/60">
                    <div className="text-lg font-bold text-slate-800">{exportResult.videos}</div>
                    <div className="text-xs text-slate-500">Videos</div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/60">
                    <div className="text-lg font-bold text-slate-800">{exportResult.photos}</div>
                    <div className="text-xs text-slate-500">Photos</div>
                  </div>
                </div>
                {exportResult.duplicates > 0 && (
                  <p className="text-xs text-emerald-700">{exportResult.duplicates} duplicate files skipped</p>
                )}
                {exportResult.elapsed_seconds && (
                  <p className="text-xs text-emerald-700 mt-1 flex items-center gap-1">
                    <Clock size={12} /> Completed in {formatDuration(exportResult.elapsed_seconds)}
                  </p>
                )}
                <p className="text-xs text-emerald-700 mt-1 font-mono">{exportResult.export_dir}</p>
              </div>
            )}
          </>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}
      </div>

      {/* Bottom action bar */}
      <div className="p-4 bg-white border-t border-slate-200">
        {/* Backup mode */}
        {mode === MODE.BACKUP && !backupDone && (
          <button onClick={handleStartBackup} disabled={!device?.found || !backupDir || busy}
            className="w-full py-2.5 px-4 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:bg-slate-300 disabled:text-slate-500 transition-colors flex items-center justify-center gap-2">
            {busy ? <><RefreshCw size={16} className="animate-spin" /> Backing up...</>
              : <><Download size={16} /> Start Backup</>}
          </button>
        )}

        {mode === MODE.BACKUP && backupDone && (
          <div className="flex gap-2">
            <button onClick={handleReset}
              className="px-4 py-2.5 rounded-xl text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 flex items-center gap-1">
              <ArrowLeft size={16} /> Home
            </button>
            <button onClick={handleBackupToExtract}
              className="flex-1 py-2.5 px-4 rounded-xl text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors flex items-center justify-center gap-2">
              <Archive size={16} /> Extract GoPro Media
            </button>
          </div>
        )}

        {/* Extract mode */}
        {mode === MODE.EXTRACT && step === STEP.PASSWORD && (
          <button onClick={handleValidateAndScan} disabled={!backupPath || !password || busy}
            className="w-full py-2.5 px-4 rounded-xl text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-slate-300 disabled:text-slate-500 transition-colors flex items-center justify-center gap-2">
            {busy ? <><RefreshCw size={16} className="animate-spin" /> Scanning...</>
              : <><Search size={16} /> Validate &amp; Scan</>}
          </button>
        )}

        {mode === MODE.EXTRACT && step === STEP.SCAN && (
          <div className="flex gap-2">
            <button onClick={() => { setStep(STEP.PASSWORD); setError(null); setScanResult(null); }}
              className="px-4 py-2.5 rounded-xl text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 flex items-center gap-1">
              <ArrowLeft size={16} /> Back
            </button>
            <button onClick={handleStartExport} disabled={!exportDir || scanResult?.total === 0 || busy}
              className="flex-1 py-2.5 px-4 rounded-xl text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-slate-300 disabled:text-slate-500 transition-colors flex items-center justify-center gap-2">
              <Download size={16} /> Export {scanResult?.total || 0} files
            </button>
          </div>
        )}

        {mode === MODE.EXTRACT && step === STEP.EXPORT && (
          <button disabled className="w-full py-2.5 px-4 rounded-xl text-sm font-medium bg-slate-300 text-slate-500 flex items-center justify-center gap-2">
            <RefreshCw size={16} className="animate-spin" /> Exporting...
          </button>
        )}

        {mode === MODE.EXTRACT && step === STEP.DONE && (
          <button onClick={handleReset}
            className="w-full py-2.5 px-4 rounded-xl text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors flex items-center justify-center gap-2">
            <RefreshCw size={16} /> Start Over
          </button>
        )}
      </div>
    </div>
  );
}
