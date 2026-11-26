document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-guide-form]");
  if (!form) return;
  const decisions = Array.from(form.querySelectorAll("[data-guide-decision]"));
  const button = form.querySelector("[data-guide-submit]");
  const blocked = button && button.disabled;
  const update = () => {
    const ready = decisions.filter((select) => select.value).length;
    form.querySelector("[data-guide-meter]").style.width = (decisions.length ? ready / decisions.length * 100 : 0) + "%";
    form.querySelector("[data-guide-count]").textContent = ready + " de " + decisions.length + " piezas listas";
    const complete = decisions.length > 0 && ready === decisions.length && !blocked;
    if (button) button.disabled = !complete;
    document.querySelector('[data-guide-step="1"]').className = complete ? "done" : "now";
    document.querySelector('[data-guide-step="2"]').className = complete ? "now" : "";
  };
  decisions.forEach((select) => select.addEventListener("change", update));
  const all = form.querySelector("[data-guide-all]");
  if (all) all.addEventListener("change", () => {
    decisions.forEach((select) => {
      select.value = Array.from(select.options).some((option) => option.value === all.value) ? all.value : "";
    });
    update();
  });
  update();
});
