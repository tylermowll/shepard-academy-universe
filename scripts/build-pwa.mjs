import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
const dist = new URL("../apps/web/dist/", import.meta.url);
const html = await readFile(new URL("index.html", dist), "utf8");
const version = createHash("sha256").update(html).digest("hex").slice(0, 16);
const shell = `/assets/app-shell-${version}.html`;
await writeFile(new URL(shell.slice(1), dist), html);
const assets = (await readdir(new URL("assets/", dist))).map(
  (name) => `/assets/${name}`,
);
const source = `const CACHE=${JSON.stringify(`math-public-${version}`)};
const ASSETS=${JSON.stringify(assets)};
const SHELL=${JSON.stringify(shell)};
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS))));
self.addEventListener('message',event=>{if(event.data==='ACTIVATE_UPDATE')self.skipWaiting();});
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('math-public-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==self.location.origin)return;
 if(ASSETS.includes(url.pathname)){event.respondWith(caches.open(CACHE).then(cache=>cache.match(event.request)).then(cached=>cached||fetch(event.request)));return;}
 if(event.request.mode==='navigate'&&url.pathname==='/'){event.respondWith(fetch(event.request).catch(()=>caches.open(CACHE).then(cache=>cache.match(SHELL))));}
});
`;
await writeFile(new URL("sw.js", dist), source);
