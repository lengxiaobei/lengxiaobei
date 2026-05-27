import { useEffect, useRef, useState } from "react";
import { openGatewaySocket } from "../api/websocket";

export function useWebSocket(onMessage?: (data: unknown) => void, enabled = true) {
  const [connected, setConnected] = useState(false);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return undefined;
    const managed = openGatewaySocket(
      (data) => {
        onMessageRef.current?.(data);
      },
      (state) => setConnected(state),
    );
    return () => managed.close();
  }, [enabled]);

  return { connected };
}
