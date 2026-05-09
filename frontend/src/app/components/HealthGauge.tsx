'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Activity, AlertTriangle, CheckCircle, XCircle, Shield, Zap, Gauge } from 'lucide-react';

interface HealthGaugeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

export function HealthGauge({ score, size = 'md', label }: HealthGaugeProps) {
  const [animated, setAnimated] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    setAnimated(false);
    setTimeout(() => setAnimated(true), 100);
  }, [score]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const sizeMap = { sm: 80, md: 120, lg: 160 };
    const s = sizeMap[size];
    canvas.width = s;
    canvas.height = s;

    const cx = s / 2;
    const cy = s / 2;
    const radius = s / 2 - 8;
    const lineWidth = 8;
    const startAngle = (Math.PI / 2) * 3;
    const endAngle = startAngle + Math.PI * 1.5;

    ctx.clearRect(0, 0, s, s);

    // Background arc
    ctx.beginPath();
    ctx.arc(cx, cy, radius, startAngle, endAngle);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Score arc with gradient
    const currentAngle = startAngle + (Math.PI * 1.5) * Math.min(score / 100, 1);
    const gradient = ctx.createConicGradient(startAngle - Math.PI / 2, cx, cy);

    if (score >= 80) {
      gradient.addColorStop(0, '#10b981');
      gradient.addColorStop(1, '#34d399');
    } else if (score >= 50) {
      gradient.addColorStop(0, '#f59e0b');
      gradient.addColorStop(1, '#fbbf24');
    } else {
      gradient.addColorStop(0, '#ef4444');
      gradient.addColorStop(1, '#f87171');
    }

    ctx.beginPath();
    ctx.arc(cx, cy, radius, startAngle, animated ? currentAngle : startAngle);
    ctx.strokeStyle = gradient;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Center text
    ctx.font = `bold ${s / 3.5}px monospace`;
    ctx.fillStyle = '#e2e8f0';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(Math.round(score) + '%', cx, cy - 4);

    // Label
    if (label && s >= 100) {
      ctx.font = `${s / 9}px sans-serif`;
      ctx.fillStyle = '#64748b';
      ctx.fillText(label, cx, cy + radius / 2 + 8);
    }
  }, [score, size, animated, label]);

  return (
    <div className="relative inline-flex items-center justify-center">
      <canvas ref={canvasRef} className="drop-shadow-lg" />
      {score >= 80 && (
        <div className="absolute -top-1 -right-1 bg-green-500/20 rounded-full p-0.5">
          <CheckCircle className="w-3 h-3 text-green-400" />
        </div>
      )}
      {score < 50 && (
        <div className="absolute -top-1 -right-1 bg-red-500/20 rounded-full p-0.5">
          <AlertTriangle className="w-3 h-3 text-red-400" />
        </div>
      )}
    </div>
  );
}