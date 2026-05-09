'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { DollarSign, AlertTriangle, Activity, Zap, Shield, RefreshCw, ChevronDown } from 'lucide-react';

interface ImpactMetrics {
  revenue_at_risk: number;
  customers_affected: number;
  uptime_percent: number;
  error_rate_percent: number;
  incidents_last_24h: number;
  mttr_minutes: number;
  mttr_with_ai_minutes?: number;
  time_saved_minutes?: number;
  trend_indicator: 'improving' | 'stable' | 'degrading' | 'unknown';
  ai_confidence: number;
  degraded_services: Array<{
    service: string;
    impact: string;
    revenue_impact: string;
  }>;
  baseline_comparison: Record<string, {
    baseline_errors: number;
    current_errors: number;
    change_percent: number;
    direction: string;
  }>;
  per_service_impact: Record<string, {
    error_count: number;
    revenue_impact: string;
    baseline_deviation_pct: number;
  }>;
  business_summary: string;
  recommendation: string;
}

interface ImpactDashboardProps {
  connected: boolean;
  onMetricsUpdate?: (m: Partial<ImpactMetrics>) => void;
}

export function ImpactDashboard({ connected, onMetricsUpdate }: ImpactDashboardProps) {
  const [metrics, setMetrics] = useState<Partial<ImpactMetrics>>({});
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

  const fetchImpact = useCallback(async () => {
    try {
      const res = await fetch('/api/impact');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMetrics(data);
      setLoading(false);
      retryRef.current = 0;

      if (data.trend_indicator === 'degrading') {
        try {
          new Notification('⚠️ DataPulse Alert', {
            body: `Error rates are increasing. ${data.revenue_at_risk ? '$' + Math.round(data.revenue_at_risk).toLocaleString() + ' revenue at risk' : 'Monitor closely'}`,
            icon: '/favicon.ico',
          });
        } catch (_) { /* Notification not allowed */ }
      }

      onMetricsUpdate?.(data);
    } catch (err) {
      console.warn('Impact fetch failed:', err);
      retryRef.current = Math.min(retryRef.current + 1, 30);
      setTimeout(fetchImpact, Math.min(retryRef.current * 1000, 30000));
    }
  }, [connected, onMetricsUpdate]);

  useEffect(() => {
    fetchImpact();
    if (!connected) return;

    const ws = new WebSocket(`ws://${window.location.host}/ws/impact`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setMetrics((prev) => ({ ...prev, ...data }));
        onMetricsUpdate?.(data);
      } catch (_) { /* ignore malformed messages */ }
    };

    ws.onclose = () => {
      console.log('Impact WS closed, polling fallback');
      fetchImpact();
    };

    const interval = setInterval(fetchImpact, 15000);
    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, [connected, fetchImpact, onMetricsUpdate]);

  const trendColors: Record<string, string> = {
    improving: 'text-green-400',
    stable: 'text-gray-400',
    degrading: 'text-red-400 animate-pulse',
    unknown: 'text-yellow-400',
  };

  const trendIcons: Record<string, string> = {
    improving: '📉',
    stable: '➡️',
    degrading: '📈',
    unknown: '❓',
  };

  const revenuePerHour = metrics.revenue_at_risk || 0;
  const potentialSavings = metrics.time_saved_minutes
    ? (revenuePerHour / 60) * metrics.time_saved_minutes
    : 0;

  return (
    <div className="space-y-4">
      {/* Top Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          icon={<DollarSign className="w-4 h-4 text-green-400" />}
          label="Revenue at Risk"
          value={`$${Math.round(revenuePerHour).toLocaleString()}/hr`}
          trend={trendIcons[metrics.trend_indicator || 'stable'] || ''}
          color="text-green-400"
          loading={loading}
        />
        <MetricCard
          icon={<AlertTriangle className="w-4 h-4 text-amber-400" />}
          label="Customers Affected"
          value={(metrics.customers_affected || 0).toLocaleString()}
          color="text-amber-400"
          loading={loading}
        />
        <MetricCard
          icon={<Activity className="w-4 h-4 text-blue-400" />}
          label="Error Rate"
          value={`${(metrics.error_rate_percent || 0).toFixed(2)}%`}
          color={(metrics.error_rate_percent || 0) > 1 ? 'text-red-400' : 'text-blue-400'}
          loading={loading}
        />
        <MetricCard
          icon={<Zap className="w-4 h-4 text-purple-400" />}
          label="AI MTTR"
          value={
            metrics.mttr_with_ai_minutes != null
              ? `${metrics.mttr_with_ai_minutes}m`
              : '—'
          }
          subtext={
            metrics.time_saved_minutes
              ? `Saves ${metrics.time_saved_minutes}min`
              : undefined
          }
          color="text-purple-400"
          loading={loading}
        />
      </div>

      {/* AI Confidence + Trend */}
      <div className="flex items-center gap-4 p-3 rounded-lg bg-gray-800/50 border border-gray-700">
        <Shield className={`w-5 h-5 ${metrics.ai_confidence >= 70 ? 'text-green-400' : metrics.ai_confidence >= 40 ? 'text-yellow-400' : 'text-red-400'}`} />
        <span className="text-sm text-gray-300">
          AI Confidence: <strong className="text-white">{metrics.ai_confidence || 0}%</strong>
        </span>
        <span className={`text-sm ${trendColors[metrics.trend_indicator || 'stable']}`}>
          {trendIcons[metrics.trend_indicator || 'stable']} Trend: <strong>{metrics.trend_indicator || 'stable'}</strong>
        </span>
        {potentialSavings > 0 && (
          <span className="ml-auto text-sm text-green-400">
            💰 Potential save: <strong>${Math.round(potentialSavings).toLocaleString()}</strong>
          </span>
        )}
      </div>

      {/* Business Summary */}
      {metrics.business_summary && (
        <div className="p-3 rounded-lg bg-amber-900/20 border border-amber-700/30">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-amber-100">{metrics.business_summary}</p>
          </div>
        </div>
      )}

      {/* Recommendation */}
      {metrics.recommendation && (
        <div className="p-3 rounded-lg bg-blue-900/20 border border-blue-700/30">
          <div className="flex items-start gap-2">
            <Shield className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-blue-100">{metrics.recommendation}</p>
          </div>
        </div>
      )}

      {/* Service Breakdown */}
      {metrics.degraded_services && metrics.degraded_services.length > 0 && (
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center justify-between p-3 bg-gray-800/50 hover:bg-gray-700/50 transition-colors"
          >
            <span className="text-sm font-medium text-gray-300">
              Degraded Services ({metrics.degraded_services.length})
            </span>
            <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${expanded ? 'rotate-180' : ''}`} />
          </button>

          {expanded && (
            <div className="divide-y divide-gray-700">
              {metrics.degraded_services.map((svc, i) => (
                <div key={i} className="p-3 flex items-center justify-between text-sm">
                  <div>
                    <span className="text-white font-medium">{svc.service}</span>
                    <span className="text-gray-400 ml-2">{svc.impact}</span>
                  </div>
                  <span className="text-amber-400 font-medium">{svc.revenue_impact}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Per-Service Impact Table */}
      {metrics.per_service_impact && Object.keys(metrics.per_service_impact).length > 0 && (
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <div className="p-3 bg-gray-800/50 border-b border-gray-700">
            <span className="text-sm font-medium text-gray-300">Service Error Breakdown</span>
          </div>
          <div className="divide-y divide-gray-700">
            {Object.entries(metrics.per_service_impact).map(([service, data]) => (
              <div key={service} className="p-3 flex items-center justify-between text-sm">
                <span className="text-white font-medium">{service}</span>
                <div className="flex items-center gap-4">
                  <span className="text-gray-400">{data.error_count} errors</span>
                  <span className={`text-xs font-bold ${data.baseline_deviation_pct > 50 ? 'text-red-400' : data.baseline_deviation_pct > 0 ? 'text-amber-400' : 'text-gray-400'}`}>
                    {data.baseline_deviation_pct > 0 ? '+' : ''}{data.baseline_deviation_pct}%
                  </span>
                  <span className="text-gray-500">{data.revenue_impact}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Baseline Comparison */}
      {metrics.baseline_comparison && Object.keys(metrics.baseline_comparison).length > 0 && (
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <div className="p-3 bg-gray-800/50 border-b border-gray-700">
            <span className="text-sm font-medium text-gray-300">Baseline Comparison (AI-Learned)</span>
          </div>
          <div className="divide-y divide-gray-700">
            {Object.entries(metrics.baseline_comparison).map(([service, data]) => (
              <div key={service} className="p-3 flex items-center justify-between text-sm">
                <span className="text-white font-medium">{service}</span>
                <div className="flex items-center gap-4">
                  <span className="text-gray-400">
                    Baseline: {data.baseline_errors}/hr → Current: {data.current_errors}/hr
                  </span>
                  <span className={`text-xs font-bold ${data.direction === 'increasing' ? 'text-red-400' : 'text-green-400'}`}>
                    {data.change_percent > 0 ? '+' : ''}{data.change_percent}% {data.direction}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-6 h-6 text-blue-400 animate-spin" />
          <span className="ml-2 text-gray-400 text-sm">Loading impact data...</span>
        </div>
      )}

      {!loading && !metrics.business_summary && (
        <div className="text-center py-8 text-gray-500">
          <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-2" />
          <p className="text-sm">All systems operational. No impact detected.</p>
        </div>
      )}
    </div>
  );
}

function MetricCard({ icon, label, value, subtext, color, trend, loading }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subtext?: string;
  color: string;
  trend?: string;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="p-4 rounded-lg bg-gray-800/50 border border-gray-700 animate-pulse">
        <div className="flex items-center gap-2 mb-2 h-4 bg-gray-700 rounded w-24" />
        <div className="h-6 bg-gray-700 rounded w-32" />
      </div>
    );
  }

  return (
    <div className="p-4 rounded-lg bg-gray-800/50 border border-gray-700 hover:border-gray-600 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500 uppercase tracking-wider">{label}</span>
        <span className={color}>{icon}</span>
      </div>
      <div className="flex items-end justify-between">
        <span className={`text-xl font-bold text-white`}>{value}</span>
        {trend && <span className="text-lg">{trend}</span>}
      </div>
      {subtext && <span className="text-xs text-gray-500 mt-1 block">{subtext}</span>}
    </div>
  );
}