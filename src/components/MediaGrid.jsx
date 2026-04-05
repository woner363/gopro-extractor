import React from 'react';
import { Film, Image } from 'lucide-react';

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function MediaItem({ file }) {
  const isVideo = file.type === 'video';
  const Icon = isVideo ? Film : Image;

  return (
    <div className="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-100 transition-colors">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
        isVideo ? 'bg-purple-100 text-purple-600' : 'bg-teal-100 text-teal-600'
      }`}>
        <Icon size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-700 truncate">{file.filename}</p>
        <p className="text-xs text-slate-400">{formatSize(file.size)}</p>
      </div>
    </div>
  );
}

export default function MediaGrid({ files = [], maxDisplay = 50 }) {
  const displayed = files.slice(0, maxDisplay);
  const remaining = files.length - maxDisplay;

  const videoCount = files.filter(f => f.type === 'video').length;
  const photoCount = files.filter(f => f.type === 'photo').length;
  const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0);

  return (
    <div>
      <div className="flex gap-4 mb-3 text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <Film size={12} /> {videoCount} videos
        </span>
        <span className="flex items-center gap-1">
          <Image size={12} /> {photoCount} photos
        </span>
        <span>{formatSize(totalSize)} total</span>
      </div>

      <div className="max-h-64 overflow-y-auto space-y-1">
        {displayed.map((file, i) => (
          <MediaItem key={i} file={file} />
        ))}
      </div>

      {remaining > 0 && (
        <p className="text-xs text-slate-400 text-center mt-2">
          +{remaining} more files
        </p>
      )}
    </div>
  );
}
