async function enablePush() {
    const status = document.getElementById("pushStatus");
  
    if (!("serviceWorker" in navigator)) {
      status.textContent = "Service Worker 非対応";
      return;
    }
    if (!("PushManager" in window)) {
      status.textContent = "Push 非対応（iOSは条件あり）";
      return;
    }
  
    // 1) 权限
    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      status.textContent = "通知が許可されませんでした";
      return;
    }
  
    // 2) 注册 SW（你 base.html 已经注册过也没事）
    const reg = await navigator.serviceWorker.ready;
  
    // 3) 取 VAPID 公钥
    const resKey = await fetch("/api/push/public-key");
    const { key } = await resKey.json();
    if (!key) {
      status.textContent = "VAPID 公開鍵が未設定です";
      return;
    }
  
    // 4) subscribe（把 base64url 公钥转成 Uint8Array）
    const appServerKey = urlBase64ToUint8Array(key);
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: appServerKey,
    });
  
    // 5) 发给后端保存
    const res = await fetch("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub),
    });
    const data = await res.json();
    if (data.ok) {
      status.textContent = "通知を有効化しました ✅";
    } else {
      status.textContent = "登録失敗";
    }
  }
  
  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    const arr = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }
  
  document.getElementById("enablePushBtn")?.addEventListener("click", enablePush);
  