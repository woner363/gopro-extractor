import React from 'react';
import { CheckCircle, XCircle, Loader, AlertCircle } from 'lucide-react';

const statusConfig = {
  connected: { icon: CheckCircle, color: 'text-emerald-500', bg: 'bg-emerald-50', border: 'border-emerald-200' },
  disconnected: { icon: XCircle, color: 'text-slate-400', bg: 'bg-slate-50', border: 'border-slate-200' },
  loading: { icon: Loader, color: 'text-blue-500', bg: 'bg-blue-50', border: 'border-blue-200' },
  warning: { icon: AlertCircle, color: 'text-amber-500', bg: 'bg-amber-50', border: 'border-amber-200' },
  error: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-50', border: 'border-red-200' },
};

export default function StatusCard({ icon: IconOverride, title, subtitle, status = 'disconnected', children }) {
  const config = statusConfig[status] || statusConfig.disconnected;
  const StatusIcon = config.icon;

  return (
    <div className={`rounded-xl border ${config.border} ${config.bg} p-4 transition-all duration-200`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {IconOverride && (
            <div className={`${config.color}`}>
              <IconOverride size={20} />
            </div>
          )}
          <div>
            <h3 className="font-medium text-slate-800 text-sm">{title}</h3>
            {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
        </div>
        <StatusIcon
          size={18}
          className={`${config.color} ${status === 'loading' ? 'animate-spin' : ''}`}
        />
      </div>
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
