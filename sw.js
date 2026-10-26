const CACHE = "acuanto-v6";
const BASE = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(BASE)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
/* Primero la red, sin usar la caché del navegador (así cada versión nueva se ve al recargar);
   sin señal, lo último guardado. */
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const misma = new URL(e.request.url).origin === location.origin;
  const pedido = misma ? fetch(e.request.url, { cache: "no-cache", credentials: "same-origin" }) : fetch(e.request);
  e.respondWith(pedido.then((r) => { const copia = r.clone(); if (r.ok && misma) caches.open(CACHE).then((c) => c.put(e.request, copia)); return r; })
    .catch(() => caches.match(e.request).then((r) => r || caches.match("index.html"))));
});
