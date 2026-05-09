'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Activity, AlertTriangle, CheckCircle, XCircle, Shield, Send, Bot, User, Loader2, MessageSquare } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  type?: 'text' | 'action' | 'alert' | 'thinking';
  metadata?: Record<string, any>;
}

interface ChatPanelProps {
  connected: boolean;
}

export function ChatPanel({ connected }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Initialize session
  useEffect(() => {
    const initSession = async () => {
      try {
        const res = await fetch('/api/chat/session', { method: 'POST' });
        const data = await res.json();
        setSessionId(data.session_id);

        // Load history
        if (data.session_id) {
          const histRes = await fetch(`/api/chat/session/${data.session_id}/history`);
          const histData = await histRes.json();
          if (histData.history?.length) {
            setMessages(histData.history.map((h: any) => ({
              id: h.id || crypto.randomUUID(),
              role: h.role as any,
              content: h.text || h.content || '',
              timestamp: h.timestamp ? new Date(h.timestamp).getTime() : Date.now(),
            })));
          }
        }

        // Setup WebSocket
        const ws = new WebSocket(`ws://${window.location.host}/ws/chat`);
        wsRef.current = ws;

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'stream') {
              // Handle streaming
              setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last && last.role === 'assistant' && last.type === 'thinking') {
                  return [...prev.slice(0, -1), {
                    ...last,
                    content: (last.content || '') + (data.content || ''),
                  }];
                }
                return [...prev, {
                  id: crypto.randomUUID(),
                  role: 'assistant',
                  content: data.content || '',
                  timestamp: Date.now(),
                  type: 'thinking',
                }];
              });
            } else if (data.type === 'done') {
              setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last && last.type === 'thinking') {
                  return [...prev.slice(0, -1), { ...last, type: 'text' }];
                }
                return prev;
              });
            } else if (data.type === 'alert') {
              setMessages(prev => [...prev, {
                id: crypto.randomUUID(),
                role: 'system',
                content: data.message || '⚠️ Alert received',
                timestamp: Date.now(),
                type: 'alert',
              }]);
            }
          } catch (_) { /* ignore */ }
        };

        ws.onclose = () => console.log('Chat WS closed');
      } catch (err) {
        console.warn('Session init failed:', err);
      }
    };

    initSession();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg.content,
          session_id: sessionId || undefined,
          mode: 'chat',
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (!res.body) throw new Error('No response body');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      let assistantMsgId = crypto.randomUUID();
      setMessages(prev => [...prev, {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        type: 'thinking',
      }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n').filter(l => l.trim());

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last && last.id === assistantMsgId && last.type === 'thinking') {
                  return [...prev.slice(0, -1), {
                    ...last,
                    content: (last.content || '') + (data.choices?.[0]?.text || data.content || ''),
                  }];
                }
                return prev;
              });
            } catch (_) { /* ignore parse errors */ }
          }
        }
      }

      // Finalize message
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last && last.id === assistantMsgId && last.type === 'thinking') {
          return [...prev.slice(0, -1), { ...last, type: 'text' }];
        }
        return prev;
      });

    } catch (err: any) {
      console.error('Chat error:', err);
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'system',
        content: `❌ Error: ${err.message}. The LLM gateway may be temporarily unavailable.`,
        timestamp: Date.now(),
        type: 'alert',
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [input, loading, sessionId]);

  const handleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }, [sendMessage]);

  const statusColor = connected ? 'bg-green-400' : 'bg-gray-500';

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-700 bg-gray-800/50">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-white">War Room Chat</span>
          <div className={`w-2 h-2 rounded-full ${statusColor} animate-pulse`} title={connected ? 'Connected' : 'Disconnected'} />
        </div>
        <span className="text-xs text-gray-500">
          Session: {sessionId ? sessionId.slice(0, 8) + '...' : 'Initializing...'}
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !loading && (
          <div className="text-center py-8 text-gray-500 text-sm">
            <Bot className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>Ask DataPulse anything about your infrastructure</p>
            <p className="mt-1 text-xs">Examples:</p>
            <ul className="mt-2 space-y-1 text-gray-400">
              <li>• "What is impacting our revenue right now?"</li>
              <li>• "What are the top 5 error-producing services?"</li>
              <li>• "Are there any unassigned shards?"</li>
              <li>• "What are the most common errors in the last hour?"</li>
            </ul>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
          >
            {msg.role === 'user' ? (
              <div className="w-7 h-7 rounded-full bg-blue-500 flex items-center justify-center flex-shrink-0">
                <User className="w-4 h-4 text-white" />
              </div>
            ) : msg.role === 'system' ? (
              <div className="w-7 h-7 rounded-full bg-yellow-500/20 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-4 h-4 text-yellow-400" />
              </div>
            ) : (
              <div className="w-7 h-7 rounded-full bg-green-500/20 flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4 text-green-400" />
              </div>
            )}

            <div
              className={`max-w-[80%] rounded-lg p-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : msg.type === 'alert'
                  ? 'bg-yellow-900/50 text-yellow-200 border border-yellow-700/50'
                  : 'bg-gray-700 text-gray-100'
              }`}
            >
              {msg.content || (msg.type === 'thinking' && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />)}
              {msg.metadata && msg.metadata.reasoning && (
                <div className="mt-1 text-xs text-gray-400 border-t border-gray-600 pt-1">
                  🤔 {msg.metadata.reasoning}
                </div>
              )}
            </div>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-gray-700 bg-gray-800/50">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder="Ask DataPulse about your infrastructure..."
            disabled={!connected || loading}
            className="flex-1 bg-gray-700 text-white rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 placeholder:text-gray-500"
          />
          <button
            onClick={sendMessage}
            disabled={!connected || loading || !input.trim()}
            className="bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          Powered by Gemini → OpenRouter → Mock fallback chain • Multi-provider LLM
        </p>
      </div>
    </div>
  );
}