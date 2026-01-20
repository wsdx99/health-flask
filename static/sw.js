const CACHE_NAME = "healthapp-v1";
const ASSETS = [
  "/",
  "/home",
  "/meals",
  "/exercises",
  "/plans",
  "/reports",
  "/static/style.css",
  "/static/manifest.json"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((res) => res || fetch(event.request))
  );
});

self.addEventListener("push", (event) => {
    let data = {};
    try { data = event.data.json(); } catch (e) {}
    const title = data.title || "健康管理";
    const options = {
      body: data.body || "今日の記録を忘れずに！",
      icon: "/static/icons/icon-192.png"
    };
    event.waitUntil(self.registration.showNotification(title, options));
  });
  