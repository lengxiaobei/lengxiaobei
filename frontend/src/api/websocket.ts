export const DEFAULT_WS_URL = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8000/ws";

export interface ManagedSocket {
  socket: WebSocket | null;
  close: () => void;
}

/** Open a WebSocket with automatic reconnection and exponential backoff. */
export function openGatewaySocket(
  onMessage: (message: unknown) => void,
  onStateChange?: (connected: boolean) => void,
): ManagedSocket {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let attempts = 0;
  let disposed = false;
  const maxDelay = 30_000;

  function connect() {
    if (disposed) return;
    try {
      socket = new WebSocket(DEFAULT_WS_URL);
    } catch {
      scheduleReconnect();
      return;
    }

    socket.addEventListener("open", () => {
      attempts = 0;
      onStateChange?.(true);
    });

    socket.addEventListener("message", (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch {
        onMessage(event.data);
      }
    });

    socket.addEventListener("close", () => {
      onStateChange?.(false);
      if (!disposed) scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // Error triggers close event, which handles reconnect
    });
  }

  function scheduleReconnect() {
    if (disposed) return;
    const delay = Math.min(1000 * 2 ** attempts, maxDelay);
    attempts++;
    reconnectTimer = setTimeout(connect, delay);
  }

  connect();

  return {
    get socket() { return socket; },
    close() {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) {
        socket.close();
        socket = null;
      }
    },
  };
}
