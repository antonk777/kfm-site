// Subscribe this browser or phone to friend-join alerts. The stats server
// pushes them, so they arrive after the tab is closed.
import { i18n } from "../i18n";
import { ref } from "vue";

export const pushReady = ref(false);

function keyBytes(base64: string): Uint8Array {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

async function publicKey(): Promise<string> {
  const res = await fetch("/api/stats/steam/push/key");
  if (!res.ok) return "";
  const data = (await res.json()) as { publicKey?: string };
  return data.publicKey || "";
}

async function postSubscription(sub: PushSubscription, unsubscribe: boolean): Promise<boolean> {
  const json = sub.toJSON();
  const res = await fetch("/api/stats/steam/push", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: sub.endpoint,
      p256dh: json.keys?.p256dh || "",
      auth: json.keys?.auth || "",
      locale: i18n.locale,
      unsubscribe,
    }),
  });
  return res.ok;
}

export async function syncDevicePush(on: boolean): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || typeof Notification === "undefined") {
    pushReady.value = false;
    return false;
  }
  try {
    if (!on) {
      const reg = await navigator.serviceWorker.getRegistration("/");
      const existing = await reg?.pushManager.getSubscription();
      if (existing) {
        await postSubscription(existing, true);
        await existing.unsubscribe();
      }
      pushReady.value = false;
      return false;
    }
    // Permission is asked only from the desktop checkbox, in the click itself.
    if (Notification.permission !== "granted") {
      pushReady.value = false;
      return false;
    }
    const key = await publicKey();
    if (!key) {
      pushReady.value = false;
      return false;
    }
    const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(key),
      });
    }
    const saved = await postSubscription(sub, false);
    pushReady.value = saved;
    return saved;
  } catch {
    pushReady.value = false;
    return false;
  }
}
