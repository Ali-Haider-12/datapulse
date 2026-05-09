'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Activity, AlertTriangle, CheckCircle2, XCircle, Shield, RefreshCw, Zap, Flame, HeartPulse } from 'lucide-react';

interface ESHealth {
  status: string;
  number_of_nodes: number;
  number_of_data_nodes: number;
  active_primary_shards: number;
  active_shards_percent?: number;
  unassigned_shards?: number;
}

interface Alert {
  id: string;
  type: 'critical' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: number;
  service?: string;
  resolved: boolean;
}

interface HealthDashboardProps {
  connected: boolean;
  onHealthUpdate?: (score: number) => void;
  onAlerts?: (alerts: Alert[]) => void;
}

export function HealthDashboard({ connected, onHealthUpdate, onAlerts }: HealthDashboardProps) {
  const [esHealth, setEsHealth] = useState<ESHealth | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [healthScore, setHealthScore] = useState(100);
  const [loading, setLoading] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/health');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.overall) {
        setEsHealth(data.overall);
      }

      if (data.score != null) {
        setHealthScore(data.score);
        onHealthUpdate?.(data.score);
      }

      if (data.alerts) {
        setAlerts(data.alerts);
        onAlerts?.(data.alerts);
      }

      setLoading(false);
    } catch (err) {
      console.warn('Health fetch failed:', err);
      setTimeout(fetchHealth, 5000);
    }
  }, [connected, onHealthUpdate, onAlerts]);

  useEffect(() => {
    fetchHealth();
    if (!connected) return;

    const ws = new WebSocket(`ws://${window.location.host}/ws/health`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.overall) setEsHealth(data.overall);
        if (data.score != null) {
          setHealthScore(data.score);
          onHealthUpdate?.(data.score);
        }
        if (data.alerts) {
          setAlerts(data.alerts);
          onAlerts?.(data.alerts);
        }
      } catch (_) { /* ignore */ }
    };

    ws.onclose = () => fetchHealth();
    const interval = setInterval(fetchHealth, 10000);
    return () => { ws.close(); clearInterval(interval); };
  }, [connected, fetchHealth, onHealthUpdate, onAlerts]);

  const generateAlerts = useCallback((): Alert[] => {
    if (!esHealth) return [];
    const genAlerts: Alert[] = [];
    const now = Date.now();

    if (esHealth.status === 'red') {
      genAlerts.push({
        id: 'alert-red',
        type: 'critical',
        title: 'Cluster Health RED',
        message: `${esHealth.unassigned_shards || 0} unassigned shards. Immediate action required.`,
        timestamp: now,
        resolved: false,
      });
    } else if (esHealth.status === 'yellow') {
      genAlerts.push({
        id: 'alert-yellow',
        type: 'warning',
        title: 'Cluster Health YELLOW',
        message: `Some shard replicas are unassigned. ${esHealth.active_shards_percent?.toFixed(1) || 'N/A'}% active shards.`,
        timestamp: now,
        resolved: false,
      });
    }

    if (esHealth.unassigned_shards && esHealth.unassigned_shards > 0) {
      genAlerts.push({
        id: 'alert-unassigned',
        type: 'critical',
        title: 'Unassigned Shards',
        message: `${esHealth.unassigned_shards} shards without assigned nodes.`,
        timestamp: now,
        resolved: false,
      });
    }

    if (healthScore < 50) {
      genAlerts.push({
        id: 'alert-score',
        type: 'warning',
        title: 'Low Health Score',
        message: `Overall health score is ${healthScore}%. Investigate immediately.`,
        timestamp: now,
        resolved: false,
      });
    }

    return genAlerts;
  }, [esHealth, healthScore]);

  const computedAlerts = alerts.length > 0 ? alerts : generateAlerts();
  const criticalCount = computedAlerts.filter(a => a.type === 'critical').length;
  const warningCount = computedAlerts.filter(a => a.type === 'warning').length;

  const healthColor = healthScore >= 80 ? 'text-green-400' : healthScore >= 50 ? 'text-yellow-400' : 'text-red-400';
  const statusColors: Record<string, string> = { green: 'text-green-400', yellow: 'text-yellow-400', red: 'text-red-400' };

  const metricCards = [
    {
      label: 'Cluster Status',
      value: esHealth?.status?.toUpperCase() || '—',
      color: statusColors[esHealth?.status || 'green'] || 'text-gray-400',
      icon: <Activity className="w-4 h-4" />,
    },
    {
      label: 'Nodes',
      value: esHealth?.number_of_nodes?.toString() || '—',
      color: 'text-blue-400',
      icon: <Shield className="w-4 h-4" />,
    },
    {
      label: 'Active Shards',
      value: esHealth?.active_primary_shards?.toString() || '—',
      color: 'text-purple-400',
      icon: <Flame className="w-4 h-4" />,
    },
    {
      label: 'Unassigned',
      value: esHealth?.unassigned_shards?.toString() || '0',
      color: esHealth?.unassigned_shards && esHealth.unassigned_shards > 0 ? 'text-red-400' : 'text-green-400',
      icon: <XCircle className="w-4 h-4" />,
    },
    {
      label: 'Critical Alerts',
      value: criticalCount.toString(),
      color: criticalCount > 0 ? 'text-red-400' : 'text-green-400',
      icon: <AlertTriangle className="w-4 h-4" />,
    },
    {
      label: 'Health Score',
      value: `${healthScore}%`,
      color: healthColor,
      icon: <HeartPulse className="w-4 h-4" />,
    },
  ];

  return (
    <div className="space-y-4">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {metricCards.map((m) => (
          <div key={m.label} className="p-3 rounded-lg bg-gray-800/50 border border-gray-700 text-center">
            <div className={`${m.color} flex items-center justify-center mb-1`}>{m.icon}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">{m.label}</div>
            <div className={`text-lg font-bold text-white mt-1 ${loading ? 'opacity-50' : ''}`}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Alerts */}
      {computedAlerts.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-300">Active Alerts</span>
            <span className="text-xs text-gray-500">{computedAlerts.length} active</span>
          </div>
          {computedAlerts.map((alert) => (
            <div
              key={alert.id}
              className={`flex items-start gap-3 p-3 rounded-lg border ${
                alert.type === 'critical'
                  ? 'bg-red-900/20 border-red-700/30'
                  : alert.type === 'warning'
                  ? 'bg-yellow-900/20 border-yellow-700/30'
                  : 'bg-gray-800/50 border-gray-700/30'
              }`}
            >
              {alert.type === 'critical' ? (
                <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
              ) : alert.type === 'warning' ? (
                <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
              )}
              <div className="flex-1">
                <p className="text-sm font-medium" style={{ color: alert.type === 'critical' ? '#fca5a5' : alert.type === 'warning' ? '#fcd34d' : '#93c5fd' }}>
                  {alert.title}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">{alert.message}</p>
              </div>
              <span className="text-xs text-gray-600 whitespace-nowrap">
                {new Date(alert.timestamp).toLocaleTimeString()}
              </span>
            </div>
          ))}
        </div>
      )}

      {!esHealth && !loading && (
        <div className="text-center py-8 text-gray-500">
          <Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Unable to reach Elasticsearch. Check your connection.</p>
        </div>
      )}
    </div>
  );
}