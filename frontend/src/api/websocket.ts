export const DEFAULT_WS_URL = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8000/ws";

export function openGatewaySocket(onMessage: (message: unknown) => void): WebSocket {
  const socket = new WebSocket(DEFAULT_WS_URL);
  socket.addEventListener("message", (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      onMessage(event.data);
    }
  });
  return socket;
}
