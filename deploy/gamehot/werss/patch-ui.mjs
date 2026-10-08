// Patch the frontend shipped in the pinned WeRSS image. Router paths stay relative to its Vite base.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
const root = process.argv[2];
function replace(file, from, to) {
  const filename = join(root, file);
  const source = readFileSync(filename, 'utf8').replace(/\r\n/g, '\n');
  if (!source.includes(from)) throw new Error(`Pinned WeRSS source changed: ${file}`);
  writeFileSync(filename, source.replaceAll(from, to));
}
replace('vite.config.ts', 'base: command === "serve" ? "/" : "/",', 'base: "/werss/",');
replace('src/api/http.ts', "(import.meta.env.VITE_API_BASE_URL || '')", "'/werss/'");
// Native URLs (not Vue Router paths) must retain the external prefix.
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const filename = join(dir, entry.name);
    if (entry.isDirectory()) walk(filename);
    else if (/\.(vue|ts|html)$/.test(entry.name) && !filename.includes('/router/')) {
      const source = readFileSync(filename, 'utf8').replace(/\r\n/g, '\n');
      writeFileSync(filename, source.replace(/(["'`])\/(static|views|api|feed|files|proxy|rss)(?=[/`$"'])/g, '$1/werss/$2')
        .replace(/href="\/add-subscription"/g, 'href="/werss/add-subscription"'));
    }
  }
}
walk(join(root, 'src'));
replace('index.html', 'href="/static/logo.svg"', 'href="/werss/static/logo.svg"');
replace('src/api/http.ts', "router.push(\"/login\")\n    }", "if (error.response?.headers?.['x-gamehot-auth'] === 'required') window.location.assign('/admin/login?return=%2Fwerss%2F');\n      else router.push(\"/login\")\n    }");
// Backend JSON carries QR, avatar and export URLs. Prefix only known local resource URLs.
replace('src/api/http.ts', '// 处理标准响应格式', `const prefixUrls = (value: any): any => {
      if (typeof value === 'string' && /^\\/(static|files|api|views|feed|proxy|rss)(\\/|$)/.test(value)) return '/werss' + value;
      if (Array.isArray(value)) return value.map(prefixUrls);
      if (value && typeof value === 'object') for (const key of Object.keys(value)) value[key] = prefixUrls(value[key]);
      return value;
    };
    response.data = prefixUrls(response.data);
    // 处理标准响应格式`);
