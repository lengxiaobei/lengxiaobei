export function useNotification() {
  return {
    notify(message: string) {
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification(message);
      }
    }
  };
}
