import React from 'react';

export default function ProgressBar({ percent = 0, message = '', size = 'md' }) {
  const heights = { sm: 'h-1.5', md: 'h-2.5', lg: 'h-4' };
  const height = heights[size] || heights.md;

  return (
    <div>
      <div className={`w-full bg-slate-200 rounded-full ${height} overflow-hidden`}>
        <div
          className={`${height} bg-blue-500 rounded-full progress-bar`}
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-xs text-slate-500 truncate max-w-[80%]">{message}</span>
        <span className="text-xs text-slate-600 font-medium">{Math.round(percent)}%</span>
      </div>
    </div>
  );
}
