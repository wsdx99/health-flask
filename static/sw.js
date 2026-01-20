const CACHE_NAME = "healthapp-v3";

// ✅ 只缓存“肯定存在”的静态资源 + 首页
// ❌ 不要缓存 /plans /reports 这种页面（它们任何一次出错都会导致 install 失败）
const CORE_ASSETS = [
  "/",
  "/home",
  "/static/style.css",
  "/static/manifest.json",
  "/static/push.js",
];

// 安装：逐个缓存，任何一个失败都不让整个 SW 失败
self.addEventListener("install", (event) => {
  self.skipWaiting(); // 立即进入 waiting->active
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);

      await Promise.allSettled(
        CORE_ASSETS.map(async (url) => {
          try {
            const res = await fetch(url, { cache: "no-store" });
            if (res.ok) {
              await cache.put(url, res);
            }
          } catch (e) {
            // 忽略单个缓存失败，保证 install 不失败
          }
        })
      );
    })()
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // 清理旧 cache
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)));
      await self.clients.claim(); // 立刻接管页面
    })()
  );
});

// fetch：cache 优先，拿不到就网络
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  event.respondWith(
    (async () => {
      const cached = await caches.match(event.request);
      if (cached) return cached;
      return fetch(event.request);
    })()
  );
});

// push 通知
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {}

  const title = data.title || "健康管理";
  const options = {
    body: data.body || "通知です",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    data: { url: data.url || "/home" },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/home";
  event.waitUntil(clients.openWindow(url));
});
