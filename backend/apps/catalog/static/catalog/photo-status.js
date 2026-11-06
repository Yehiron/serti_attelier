(() => {
  "use strict";
  function init() {
    const monitor = document.querySelector("[data-photo-monitor]");
    if (!monitor) return;
    const statusUrl = monitor.dataset.statusUrl;
    let timer, controller, started = Date.now(), delay = 3000, stopped = false;
    let wasPending = false;
    const timeoutMessage = "El procesamiento está tardando más de lo normal. Puedes seguir editando y volver más tarde.";
    function stop() {
      stopped = true;
      clearTimeout(timer);
      if (controller) controller.abort();
    }
    window.addEventListener("pagehide", stop, {once: true});
    function schedule() {
      if (stopped) return;
      if (Date.now() - started >= 180000) {
        monitor.textContent = timeoutMessage;
        return;
      }
      timer = setTimeout(poll, Math.min(delay, 180000 - (Date.now() - started)));
      delay = Math.min(15000, delay * 1.5);
    }
    function render(photo) {
      const label = document.querySelector(`[data-photo-id="${photo.id}"]`);
      if (!label) return;
      label.dataset.photoStatus = photo.status;
      label.textContent = {pending: "Procesando…", ready: "Lista", failed: "No se pudo procesar"}[photo.status];
      if (photo.status === "failed" && monitor.dataset.canRetry) {
        const button = document.createElement("button");
        button.type = "submit";
        button.textContent = "Reintentar";
        button.dataset.photoRetry = photo.id;
        button.formMethod = "post";
        button.formAction = statusUrl.replace(/status\/$/, `${photo.id}/retry/`);
        button.formNoValidate = true;
        label.append(" ", button);
      }
      const preview = document.querySelector(`[data-photo-preview="${photo.id}"]`);
      if (preview && photo.thumb_url) {
        const img = document.createElement("img");
        img.src = photo.thumb_url;
        img.alt = "";
        img.width = 64;
        img.height = 80;
        img.style.objectFit = "contain";
        preview.replaceChildren(img);
      }
    }
    async function poll() {
      if (stopped) return;
      if (Date.now() - started >= 180000) { monitor.textContent = timeoutMessage; return; }
      controller = new AbortController();
      const abortTimer = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch(statusUrl, {credentials: "same-origin", signal: controller.signal});
        if (!response.ok) throw new Error("status");
        const data = await response.json();
        if (stopped) return;
        data.photos.forEach(render);
        document.dispatchEvent(new CustomEvent("catalog:photo-status", {detail: data}));
        const pending = data.photos.some(p => p.status === "pending");
        if (wasPending && data.photos.some(p => p.is_primary && p.status === "ready")) {
          monitor.textContent = data.ready_to_publish ? "Las fotos están listas. Ya puedes publicar." : "Las fotos están listas.";
        }
        wasPending = pending;
        if (pending) schedule();
      } catch (_) {
        if (!stopped) schedule();
      } finally { clearTimeout(abortTimer); }
    }
    document.addEventListener("click", async event => {
      const button = event.target.closest("[data-photo-retry]");
      if (!button || !monitor.dataset.canRetry) return;
      event.preventDefault();
      button.disabled = true;
      try {
        const response = await fetch(button.formAction, {
          method: "POST", credentials: "same-origin",
          headers: {"X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]').value, "Accept": "application/json"}
        });
        if (!response.ok) throw new Error("retry");
        clearTimeout(timer);
        started = Date.now(); delay = 3000; wasPending = true;
        monitor.textContent = "Procesando…";
        await poll();
      } catch (_) {
        monitor.textContent = "No se pudo solicitar el reintento. Recarga la página e inténtalo de nuevo.";
        button.disabled = false;
      }
    });
    if (document.querySelector('[data-photo-status="pending"][data-photo-id]:not([data-photo-id=""])')) {
      wasPending = true;
      schedule();
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
