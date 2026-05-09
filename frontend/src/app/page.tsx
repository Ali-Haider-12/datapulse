'use client';

import { useState, useEffect, useCallback } from 'react';
import { Activity, Shield, Settings, Radio, Zap, Menu, Bell, Search, AlertTriangle } from 'lucide-react';
import { Dashboard } from './components/Dashboard';

/* ── Patrol View (simplified) ── */
function PatrolView({ connected }: { connected: boolean }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center">
        <Radio className="w-16 h-16 mx-auto mb-4 text-blue-400 animate-pulse" />
        <h2 className="text-xl font-bold text-white mb-2">Patrol Service</h2>
        <p className="text-gray-400">
          {connected ? 'Active — monitoring scheduled sweeps' : 'Connecting...'}
        </p>
        <div className="mt-4 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-left text-sm text-gray-300 max-w-sm mx-auto">
          <p>• Scheduled ES health sweeps</p>
          <p>• Automatic incident detection</p>
          <p>• Threshold-based alerting</p>
          <p>• Patrol history logging</p>
        </div>
      </div>
    </div>
  );
}

/* ── War Room View (simplified) ── */
function WarRoomView({ connected }: { connected: boolean }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center">
        <AlertTriangle className="w-16 h-16 mx-auto mb-4 text-red-400" />
        <h2 className="text-xl font-bold text-white mb-2">War Room</h2>
        <p className="text-gray-400">
          Multi-agent incident response system
        </p>
        <div className="mt-4 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-left text-sm text-gray-300 max-w-sm mx-auto space-y-2">
          <p>🟢 <strong>Detector Agent</strong> — Monitors ES health</p>
          <p>🔵 <strong>Investigator Agent</strong> — Root cause analysis</p>
          <p>🟠 <strong>Fixer Agent</strong> — Automated remediation</p>
          <p className="text-gray-500 mt-2">Access via POST /api/warroom</p>
        </div>
      </div>
    </div>
  );
}

/* ── Settings View ── */
function SettingsView() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-lg mx-auto">
        <Settings className="w-16 h-16 mx-auto mb-4 text-gray-400" />
        <h2 className="text-xl font-bold text-white mb-4">Settings</h2>
        <div className="space-y-3 text-left">
          <div className="p-3 bg-gray-800/50 rounded-lg border border-gray-700">
            <p className="text-sm text-gray-400 mb-1">LLM Fallback Chain</p>
            <p className="text-sm text-white">Gemini API → OpenRouter → Deepseek → Mock</p>
          </div>
          <div className="p-3 bg-gray-800/50 rounded-lg border border-gray-700">
            <p className="text-sm text-gray-400 mb-1">Elasticsearch</p>
            <p className="text-sm text-white">MCP Client + Direct ES API fallback</p>
          </div>
          <div className="p-3 bg-gray-800/50 rounded-lg border border-gray-700">
            <p className="text-sm text-gray-400 mb-1">Features</p>
            <ul className="text-sm text-gray-300 list-disc list-inside space-y-1">
              <li>Real-time health monitoring (WebSocket)</li>
              <li>AI-powered business impact scoring</li>
              <li>Multi-agent war room (async)</li>
              <li>Voice command support (Twilio)</li>
              <li>Auto-generated postmortems</li>
              <li>Query caching with TTL</li>
              <li>Session persistence & auto-recovery</li>
            </ul>
          </div>
          <div className="p-3 bg-amber-900/20 rounded-lg border border-amber-700/30">
            <p className="text-sm text-amber-200">
              <strong>Version:</strong> DataPulse v2.1.0<br />
              <strong>License:</strong> MIT<br />
              <strong>Repo:</strong> Ali-Haider-12/datapulse
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Main App ── */
export default function Home() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [connected, setConnected] = useState(false);
  const [alertCount, setAlertCount] = useState(0);
  const [wsRetryCount, setWsRetryCount] = useState(0);

  // Connection status WebSocket
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimeout: ReturnType<typeof setTimeout>;
    let mounted = true;

    const connect = () => {
      if (!mounted) return;
      try {
        ws = new WebSocket(`ws://${window.location.host}/ws/health`);
        ws.onopen = () => { setConnected(true); setWsRetryCount(0); };
        ws.onclose = () => {
          setConnected(false);
          if (mounted) {
            const delay = Math.min(1000 * Math.pow(2, wsRetryCount), 30000);
            retryTimeout = setTimeout(() => {
              setWsRetryCount(prev => prev + 1);
              connect();
            }, delay);
          }
        };
      } catch {
        if (mounted) {
          retryTimeout = setTimeout(connect, 3000);
        }
      }
    };

    connect();
    return () => {
      mounted = false;
      if (ws) ws.close();
      clearTimeout(retryTimeout);
    };
  }, [wsRetryCount]);

  // Alert count updates via broadcast
  const handleAlertUpdate = useCallback((count: number) => {
    setAlertCount(count);
  }, []);

  const TABS = [
    { id: 'dashboard', label: 'Dashboard', icon: <Zap className="w-4 h-4" /> },
    { id: 'warroom', label: 'War Room', icon: <AlertTriangle className="w-4 h-4" /> },
    { id: 'patrol', label: 'Patrol', icon: <Radio className="w-4 h-4" /> },
    { id: 'settings', label: 'Settings', icon: <Settings className="w-4 h-4" /> },
  ];

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white overflow-hidden">
      {/* Compact Top Bar */}
      <header className="h-11 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => setActiveTab('dashboard')} className="flex items-center gap-2 hover:opacity-80">
            <HeartPulse className={`w-5 h-5 ${connected ? 'text-green-400 animate-pulse' : 'text-gray-500'}`} />
            <span className="text-base font-bold bg-gradient-to-r from-green-400 to-emerald-400 bg-clip-text text-transparent">
              DataPulse
            </span>
          </button>
          <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-gray-500'}`} />
          <span className="text-[10px] text-gray-600">{connected ? 'LIVE' : 'RECONNECTING'}</span>
        </div>
        <div className="flex items-center gap-3">
          {alertCount > 0 && (
            <span className="text-xs text-amber-400 flex items-center gap-1">
              <Bell className="w-3 h-3" />{alertCount}
            </span>
          )}
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
            healthScorePreview >= 80 ? 'bg-green-500/20 text-green-400' :
            healthScorePreview >= 50 ? 'bg-yellow-500/20 text-yellow-400' :
            'bg-red-500/20 text-red-400'
          }`}>
            {healthScorePreview}%
          </span>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="flex items-center gap-1 px-3 py-1.5 bg-gray-900/50 border-b border-gray-800 shrink-0">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeTab === tab.id
                ? 'bg-gray-700/50 text-white'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-700/30'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="flex-1 overflow-hidden">
        {activeTab === 'dashboard' && <Dashboard onAlerts={(alerts: any[]) => setAlertCount(alerts.filter((a: any) => !a.resolved).length)} />}
        {activeTab === 'warroom' && <WarRoomView connected={connected} />}
        {activeTab === 'patrol' && <PatrolView connected={connected} />}
        {activeTab === 'settings' && <SettingsView />}
      </main>

      {/* Status Bar */}
      <footer className="h-5 bg-gray-900 border-t border-gray-800 flex items-center justify-between px-4 text-[10px] text-gray-600 shrink-0">
        <span className="flex items-center gap-2">
          Gemini → OpenRouter → Mock fallback • v2.1.0
        </span>
        <span>{new Date().toLocaleTimeString()}</span>
      </footer>
    </div>
  );
}

// Dummy for conditional health score
let healthScorePreview = 100;
if (typeof window !== 'undefined') {
  // This will be set via the HealthDashboard onHealthUpdate callback
}