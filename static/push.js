(async () => {
    const btn = document.getElementById("enablePushBtn");
    const status = document.getElementById("pushStatus");
    if (!btn || !status) return;
  
    function setStatus(msg) { status.textContent = msg; }
  
    function urlBase64ToUint8Array(base64String) {
      const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
      const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
      const raw = atob(base64);
      const arr = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
      return arr;
    }
  
    btn.addEventListener("click", async () => {
      try {
        setStatus("1/6: 確認中...");
  
        if (!("serviceWorker" in navigator)) {
          setStatus("Service Worker 非対応");
          return;
        }
        if (!("Notification" in window)) {
          setStatus("Notification 非対応");
          return;
        }
        if (!("PushManager" in window)) {
          setStatus("Push 非対応（iOSはPWA+16.4+が必要）");
          return;
        }
  
        setStatus("2/6: 権限をリクエスト...");
        const perm = await Notification.requestPermission();
        if (perm !== "granted") {
          setStatus("通知が許可されませんでした");
          return;
        }
  
        setStatus("3/6: Service Worker 準備中...");
        const reg = await navigator.serviceWorker.ready;
  
        setStatus("4/6: 公開鍵取得中...");
        const resKey = await fetch("/api/push/public-key", { cache: "no-store" });
        const keyJson = await resKey.json();
        const publicKey = keyJson.key;
        if (!publicKey) {
          setStatus("VAPID 公開鍵が未設定（Renderの環境変数）");
          return;
        }
  
        setStatus("5/6: 購読作成中...");
        let sub = await reg.pushManager.getSubscription();
        if (!sub) {
          sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(publicKey),
          });
        }
  
        setStatus("6/6: サーバー登録中...");
        const res = await fetch("/api/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(sub),
        });
  
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) {
          setStatus("登録失敗: " + (data.error || res.status));
          return;
        }
  
        // endpoint 末尾显示一下，证明真的有订阅
        const ep = sub.endpoint || "";
        setStatus("通知を有効化しました ✅ (" + ep.slice(-16) + ")");
      } catch (e) {
        setStatus("エラー: " + (e && e.message ? e.message : e));
      }
    });
  })();
  