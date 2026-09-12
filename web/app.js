function imageApp() {
  return {
    files: [],
    dragging: false,
    width: '',
    height: '',
    mode: 'fit',
    format: 'jpeg',
    quality: 82,
    processing: false,
    error: '',
    resultUrl: null,
    resultName: 'result',
    resultIsImage: true,

    get modeHint() {
      const hints = {
        fit: 'Вписать с сохранением пропорций — можно указать только одну сторону.',
        cover: 'Заполнить область и обрезать по центру — нужны ширина и высота.',
        crop: 'Обрезать по центру без масштабирования — нужны ширина и высота.',
      };
      return hints[this.mode] || '';
    },

    addFiles(fileList) {
      const list = Array.from(fileList || []);
      const accepted = list.filter((f) =>
        ['image/jpeg', 'image/png'].includes(f.type) || /\.(jpe?g|png)$/i.test(f.name)
      );
      accepted.forEach((file) => this.files.push({ file, url: URL.createObjectURL(file) }));
      const rejected = list.length - accepted.length;
      if (rejected > 0) {
        this.error = `Пропущено файлов: ${rejected}. Поддерживаются только JPEG и PNG.`;
      }
      this.$refs.fileInput.value = '';
    },

    removeFile(index) {
      URL.revokeObjectURL(this.files[index].url);
      this.files.splice(index, 1);
      this.clearResult();
    },

    clearAll() {
      this.files.forEach((f) => URL.revokeObjectURL(f.url));
      this.files = [];
      this.clearResult();
    },

    clearResult() {
      if (this.resultUrl) URL.revokeObjectURL(this.resultUrl);
      this.resultUrl = null;
    },

    formatSize(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    },

    async process() {
      if (!this.files.length) return;

      const width = this.width ? parseInt(this.width, 10) : null;
      const height = this.height ? parseInt(this.height, 10) : null;

      if ((this.mode === 'cover' || this.mode === 'crop') && (!width || !height)) {
        this.error = 'Для этого режима нужно указать и ширину, и высоту.';
        return;
      }

      this.processing = true;
      this.error = '';
      this.clearResult();

      try {
        const form = new FormData();
        if (this.files.length === 1) {
          form.append('file', this.files[0].file);
        } else {
          this.files.forEach((f) => form.append('files', f.file));
        }
        if (width) form.append('width', width);
        if (height) form.append('height', height);
        form.append('mode', this.mode);
        form.append('format', this.format);
        form.append('quality', this.quality);

        const endpoint = this.files.length === 1 ? '/v1/process' : '/v1/process/batch';
        const res = await fetch(endpoint, { method: 'POST', body: form });

        if (!res.ok) {
          let detail = res.statusText;
          try {
            const json = await res.json();
            detail = json.detail || json.message || detail;
          } catch (_) {}
          throw new Error(`Ошибка ${res.status}: ${detail}`);
        }

        const blob = await res.blob();
        this.resultUrl = URL.createObjectURL(blob);
        this.resultName = this.filenameFrom(res) || (this.files.length === 1 ? 'result' : 'results.zip');
        this.resultIsImage = blob.type.startsWith('image/');
      } catch (err) {
        this.error = err.message || 'Не удалось обработать изображения';
      } finally {
        this.processing = false;
      }
    },

    filenameFrom(res) {
      const cd = res.headers.get('Content-Disposition');
      if (!cd) return null;
      const m = cd.match(/filename="([^"]+)"/);
      return m ? m[1] : null;
    },

    download() {
      if (!this.resultUrl) return;
      const a = document.createElement('a');
      a.href = this.resultUrl;
      a.download = this.resultName;
      document.body.appendChild(a);
      a.click();
      a.remove();
    },
  };
}
