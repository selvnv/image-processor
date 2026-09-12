# Image Processor

Микросервис ресайза/сжатия изображений на FastAPI. Исходники нигде не
сохраняются: обработка идёт в памяти, результат отдаётся сразу в ответе. Без
БД и аутентификации.

## Запуск

```bash
docker compose up --build
```

- **UI:** `http://localhost`
- **API:** `http://localhost/v1/...` (за nginx)
- **Healthcheck:** `http://localhost/health`

Фронтенд — статическая страница (Tailwind CSS + Alpine.js), которую отдаёт
nginx. API проксируется на FastAPI.

## API

### Одиночная обработка

`POST /v1/process` (`multipart/form-data`)

| Поле    | Тип          | Описание                                                        |
| ------- | ------------ | --------------------------------------------------------------- |
| file    | file         | исходник jpg/jpeg/png (обязательно)                              |
| width   | int          | целевая ширина, px                                               |
| height  | int          | целевая высота, px                                               |
| mode    | fit/cover/crop | `fit` — вписать с сохранением пропорций; `cover` — заполнить и обрезать по центру; `crop` — обрезать по центру без масштабирования |
| format  | jpeg/webp    | выходной формат (default: `jpeg`)                                |
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
- Tailwind подключён через Play CDN — для продакшена стоит собрать и
  завендорить CSS вместо CDN.
