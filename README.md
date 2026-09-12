# Image Processor

Микросервис ресайза/сжатия изображений на FastAPI. Исходники нигде не
сохраняются: обработка идёт в памяти, результат отдаётся сразу в ответе. Без
БД и аутентификации.

## Запуск

Есть два режима: полный стек (со встроенным nginx) и только приложение
(под внешний nginx).

### Полный стек (встроенный nginx)

```bash
docker compose --profile web up --build
```

- **UI:** `http://localhost`
- **API:** `http://localhost/v1/...` (за nginx)
- **Healthcheck:** `http://localhost/health`

### Только приложение (внешний nginx)

Если на сервере уже стоит свой nginx, запускаем только backend:

```bash
docker compose up --build
```

FastAPI слушает `127.0.0.1:8000` и отвечает только на API. Статику фронтенда
собираем один раз и кладём в каталог, который раздаёт внешний nginx:

```bash
cd web
npm install
npm run build   # соберёт в web/dist
# скопировать содержимое web/dist в корень nginx (например /var/www/image-processor)
```

Пример конфига внешнего nginx:

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 20m;

    root /var/www/image-processor;
    index index.html;

    location /v1/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
```

Фронтенд — статическая страница (Tailwind CSS + Alpine.js). В полном стеке её
отдаёт встроенный nginx; в режиме с внешним nginx — сам nginx с каталога на
диске. API проксируется на FastAPI.

## API

### Одиночная обработка

`POST /v1/process` (`multipart/form-data`)

| Поле    | Тип          | Описание                                                        |
| ------- | ------------ | --------------------------------------------------------------- |
| file    | file         | исходник jpg/jpeg/png (обязательно)                              |
| width   | int          | целевая ширина, px                                               |
| height  | int          | целевая высота, px                                               |
| mode    | fit/cover/crop | `fit` — вписать с сохранением пропорций; `cover` — заполнить и обрезать по центру; `crop` — обрезать по центру без масштабирования |
| format  | jpeg/webp/png/original | выходной формат (default: `original` — исходный формат файла)   |
| quality | 1..100       | качество сжатия (default: `82`)                                  |

`mode=cover` и `mode=crop` требуют одновременно `width` и `height`.

### Пакетная обработка

`POST /v1/process/batch` — принимает несколько файлов (`files`) с теми же
параметрами, возвращает ZIP-архив с результатами и `manifest.json`
(в `manifest.json` — список успешных файлов и ошибок).

### Healthcheck

`GET /health`

## Примеры

```bash
# Ресайз в WebP
curl -X POST http://localhost/v1/process \
  -F "file=@photo.png" -F "width=800" \
  -F "format=webp" -F "quality=80" -o result.webp

# Обрезка по центру (cover)
curl -X POST http://localhost/v1/process \
  -F "file=@photo.jpg" -F "width=300" -F "height=300" \
  -F "mode=cover" -o avatar.jpg

# Несколько файлов → ZIP
curl -X POST http://localhost/v1/process/batch \
  -F "files=@a.jpg" -F "files=@b.png" \
  -F "width=500" -F "format=webp" -o results.zip
```

## Ограничения

- Входные форматы: JPEG, PNG (`jpg` — это JPEG).
- Максимальный размер файла: 20 МБ (nginx `client_max_body_size`).
- Максимум пикселей на изображение: 40 МП (защита от decompression-bomb).
- `mode=fit` не увеличивает изображение (только вписывает/уменьшает).
- Tailwind и Alpine.js завендорены при сборке образа — внешних CDN нет.
