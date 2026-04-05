import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Hook for communicating with the Python backend via Electron IPC.
 */
export function useBackend() {
  const [progress, setProgress] = useState(null);
  const cleanupRef = useRef(null);

  useEffect(() => {
    if (!window.electronAPI) return;

    const cleanup = window.electronAPI.onPythonNotification((data) => {
      if (data.method === 'progress') {
        setProgress(data.params);
      }
    });
    cleanupRef.current = cleanup;

    return () => {
      if (cleanupRef.current) cleanupRef.current();
    };
  }, []);

  const callBackend = useCallback(async (method, params) => {
    if (!window.electronAPI) {
      // Dev mode fallback - simulate responses
      console.warn('electronAPI not available, using mock data');
      return getMockResponse(method);
    }
    return window.electronAPI.callPython(method, params);
  }, []);

  const clearProgress = useCallback(() => setProgress(null), []);

  return { callBackend, progress, clearProgress };
}

/**
 * Hook for directory selection dialog.
 */
export function useDirectoryPicker() {
  const pickDirectory = useCallback(async () => {
    if (!window.electronAPI) return null;
    return window.electronAPI.selectDirectory();
  }, []);

  return { pickDirectory };
}

// Mock responses for development without Electron
function getMockResponse(method) {
  const mocks = {
    check_environment: {
      libimobiledevice: true,
      python: true,
      ffprobe: false,
      ready: true,
    },
    detect_device: {
      found: true,
      udid: 'MOCK-UDID-12345',
      name: 'iPad Pro',
      product_type: 'iPad13,4',
      ios_version: '18.3',
    },
    get_stats: {
      total_files: 42,
      total_bytes: 1024 * 1024 * 500,
    },
  };
  return mocks[method] || {};
}
