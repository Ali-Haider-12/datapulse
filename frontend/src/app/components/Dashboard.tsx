'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { AlertTriangle, Zap, CheckCircle, Activity, HeartPulse, MessageSquare } from 'lucide-react';
import { HealthDashboard } from './HealthDashboard';
import { ImpactDashboard } from './ImpactDashboard';
import { ChatPanel } from './ChatPanel';

type DashboardTab = 'impact' | 'health';

export function Dashboard() {
  const [connected, setConnected] = useState(false);
  const [dashboardTab, setDashboardTab] = useState<DashboardTab>('impact');
  const [healthScore, setHealthScore] = useState(100);
  const [alertCount, setAlertCount] = useState(0);
  const [wsRetryCount, setWsRetryCount] = useState(0);

  // Main WebSocket for connection status
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimeout: NodeJS.Timeout;

    const connect = () => {
      try {
        ws = new WebSocket(`ws://${window.location.host}/ws/health`);

        ws.onopen = () => {
          setConnected(true);
          setWsRetryCount(0);
        };

        ws.onclose = () => {
          setConnected(false);
          // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
          const delay = Math.min(1000 * Math.pow(2, wsRetryCount), 30000);
          retryTimeout = setTimeout(() => {
            setWsRetryCount(prev => prev + 1);
            connect();
          }, delay);
        };
      } catch (err) {
        setConnected(false);
        retryTimeout = setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      if (ws) ws.close();
      clearTimeout(retryTimeout);
    };
  }, [wsRetryCount]);

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white">
      {/* Top Bar */}
      <header className="h-12 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <HeartPulse className={`w-5 h-5 ${connected ? 'text-green-400 animate-pulse' : 'text-gray-500'}`} />
            <span className="text-lg font-bold bg-gradient-to-r from-green-400 to-emerald-400 bg-clip-text text-transparent">
              DataPulse
            </span>
            <span className="text-xs text-gray-500 font-normal">AI ES Monitor</span>
          </div>
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-gray-500'}`} />
          <span className="text-xs text-gray-500">
            {connected ? 'Live' : 'Reconnecting...'}
          </span>
        </div>
        <div className="flex items-center gap-4">
          {alertCount > 0 && (
            <span className="flex items-center gap-1 text-sm text-amber-400">
              <AlertTriangle className="w-4 h-4" />
              {alertCount} alerts
            </span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            healthScore >= 80 ? 'bg-green-500/20 text-green-400' :
            healthScore >= 50 ? 'bg-yellow-500/20 text-yellow-400' :
            'bg-red-500/20 text-red-400'
          }`}>
            Health: {healthScore}%
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex">
          {/* Left: Dashboard */}
          <div className="w-1/2 border-r border-gray-800 flex flex-col overflow-hidden">
            <div className="flex border-b border-gray-800 shrink-0">
              <button
                onClick={() => setDashboardTab('impact')}
                className={`flex-1 py-2 text-sm font-medium flex items-center justify-center gap-1.5 transition-colors ${
                  dashboardTab === 'impact'
                    ? 'text-green-400 border-b-2 border-green-400 bg-gray-900/50'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                <Zap className="w-4 h-4" />
                Business Impact
              </button>
              <button
                onClick={() => setDashboardTab('health')}
                className={`flex-1 py-2 text-sm font-medium flex items-center justify-center gap-1.5 transition-colors ${
                  dashboardTab === 'health'
                    ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-900/50'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                <Activity className="w-4 h-4" />
                Infrastructure
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {connected ? (
                dashboardTab === 'impact' ? (
                  <ImpactDashboard
                    connected={connected}
                    onMetricsUpdate={(m: any) => {
                      if (m.customers_affected) {
                        // Update alert count based on metrics
                      }
                    }}
                  />
                ) : (
                  <HealthDashboard
                    connected={connected}
                    onHealthUpdate={(score: number) => setHealthScore(score)}
                    onAlerts={(alerts: any[]) => setAlertCount(alerts.filter((a: any) => !a.resolved).length)}
                  />
                )
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <div className="text-center">
                    <Activity className="w-12 h-12 mx-auto mb-3 animate-spin text-gray-600" />
                    <p className="text-sm">Connecting to DataPulse...</p>
                    <p className="text-xs text-gray-600 mt-1">Attempt {wsRetryCount + 1}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right: Chat */}
          <div className="w-1/2 flex flex-col overflow-hidden">
            <ChatPanel connected={connected} />
          </div>
        </div>
      </main>

      {/* Status Bar */}
      <footer className="h-6 bg-gray-900 border-t border-gray-800 flex items-center justify-between px-4 text-xs text-gray-600 shrink-0">
        <span>Gemini → OpenRouter → Mock fallback</span>
        <span>{new Date().toLocaleTimeString()}</span>
      </footer>
    </div>
  );
}