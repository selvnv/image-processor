const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

fs.mkdirSync('dist/css', { recursive: true });
fs.mkdirSync('dist/js', { recursive: true });
fs.mkdirSync('dist/fonts/files', { recursive: true });

// Compile Tailwind CSS
execSync('npx tailwindcss -i ./input.css -o ./dist/css/tailwind.css --minify', { stdio: 'inherit' });

// Vendor Alpine.js
fs.copyFileSync('node_modules/alpinejs/dist/cdn.min.js', 'dist/js/alpine.min.js');

// Self-host fonts (@font-face rules + woff2 files)
const fontCss = [
  'node_modules/@fontsource/exo-2/400.css',
  'node_modules/@fontsource/exo-2/500.css',
  'node_modules/@fontsource/exo-2/600.css',
  'node_modules/@fontsource/play/400.css',
  'node_modules/@fontsource/play/700.css',
].map((f) => fs.readFileSync(f, 'utf8')).join('\n');
fs.writeFileSync('dist/fonts/fonts.css', fontCss);

for (const dir of [
  'node_modules/@fontsource/exo-2/files',
  'node_modules/@fontsource/play/files',
]) {
  for (const f of fs.readdirSync(dir)) {
    fs.copyFileSync(path.join(dir, f), path.join('dist/fonts/files', f));
  }
}

// Static entry files
fs.copyFileSync('index.html', 'dist/index.html');
fs.copyFileSync('app.js', 'dist/app.js');
fs.cpSync('img', 'dist/img', { recursive: true });

console.log('Frontend build complete');
