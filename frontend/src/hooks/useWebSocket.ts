import { useEffect, useState } from "react";
import { openGatewaySocket } from "../api/websocket";

export function useWebSocket(enabled = true) {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<unknown>();

  useEffect(() => {
    if (!enabled) return undefined;
    const socket = openGatewaySocket(setLastMessage);
    socket.addEventListener("open", () => setConnected(true));
    socket.addEventListener("close", () => setConnected(false));
    return () => socket.close();
  }, [enabled]);

  return { connected, lastMessage };
}
