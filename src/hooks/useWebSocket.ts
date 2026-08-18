'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { wsManager } from '@/lib/ws';
import { useStore } from '@/lib/store';
import type { LivePrice, Opportunity } from '@/lib/store';

interface UseWebSocketOptions {
  autoConnect?: boolean;
  token?: string | null;
}

interface UseWebSocketReturn {
  connected: boolean;
  lastMessage: unknown;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { autoConnect = true, token } = options;
  const [connected, setConnected] = useState(wsManager.connected);
  const [lastMessage, setLastMessage] = useState(wsManager.lastMessage);
  const storeRef = useRef(useStore);

  const connect = useCallback(() => {
    const t = token ?? localStorage.getItem('ultrabot_token');
    wsManager.connect(t ?? undefined);
  }, [token]);

  useEffect(() => {
    // Subscribe to connection state
    const unsubConnected = wsManager.on('connected', () => setConnected(true));
    const unsubDisconnected = wsManager.on('disconnected', () => setConnected(false));

    // Subscribe to all messages for lastMessage tracking
    const unsubMessage = wsManager.on('message', (msg) => {
      setLastMessage(msg);
    });

    // Dispatch live price updates to store
    const unsubPrices = wsManager.on('live_price_updates', (data) => {
      const store = storeRef.current.getState();
      if (Array.isArray(data)) {
        store.realtime.updatePrices(data as LivePrice[]);
      } else if (data && typeof data === 'object' && 'symbol' in (data as LivePrice)) {
        store.realtime.updatePrice(data as LivePrice);
      }
    });

    // Dispatch new opportunities to store
    const unsubOpps = wsManager.on('new_opportunity', (data) => {
      const store = storeRef.current.getState();
      if (data && typeof data === 'object') {
        store.realtime.addOpportunity(data as Opportunity);
      }
    });

    // Dispatch engine status updates to store
    const unsubEngine = wsManager.on('engine_status', (data) => {
      const store = storeRef.current.getState();
      if (data && typeof data === 'object') {
        const engine = data as Record<string, unknown>;
        if (typeof engine.status === 'string') {
          store.engine.setEngineStatus(engine.status as 'running' | 'stopped' | 'paused');
        }
        if (typeof engine.broker === 'string') {
          store.engine.setActiveBroker(engine.broker);
        }
        if (typeof engine.regime === 'string') {
          store.engine.setRegime(engine.regime as 'bull' | 'bear' | 'sideways' | 'volatile');
        }
        if (typeof engine.vix === 'number') {
          store.engine.setVix(engine.vix);
        }
        if (typeof engine.nifty_value === 'number') {
          store.engine.setNifty(
            engine.nifty_value,
            (engine.nifty_change as number) ?? 0,
          );
        }
        if (typeof engine.market_close_seconds === 'number') {
          store.engine.setMarketCloseSeconds(engine.market_close_seconds);
        }
      }
    });

    // Dispatch scan telemetry updates to store
    const handleTelemetry = (data: any) => {
      const store = storeRef.current.getState();
      if (!data) return;
      if (data.type === 'scan_telemetry_event' && data.event) {
        store.engine.addTelemetryEvent(data.event);
      } else if (data.type === 'scan_telemetry' && data.telemetry) {
        store.engine.setScanTelemetry(data.telemetry);
        if (data.telemetry.broker) {
          store.engine.setActiveBroker(data.telemetry.broker);
        }
      } else if (data.recent_events || data.total_scans !== undefined) {
        store.engine.setScanTelemetry(data);
        if (data.broker) {
          store.engine.setActiveBroker(data.broker);
        }
      }
    };

    const unsubTelemetry = wsManager.on('telemetry', handleTelemetry);
    const unsubScanTelemetry = wsManager.on('scan_telemetry', handleTelemetry);

    // Auto-connect on mount
    if (autoConnect) {
      connect();
    }

    return () => {
      unsubConnected();
      unsubDisconnected();
      unsubMessage();
      unsubPrices();
      unsubOpps();
      unsubEngine();
      unsubTelemetry();
      unsubScanTelemetry();
    };
  }, [autoConnect, connect]);

  return { connected, lastMessage };
}

export default useWebSocket;
