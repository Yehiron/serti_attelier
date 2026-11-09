(() => {
  function update() {
    document.querySelectorAll('input[maxlength], textarea[maxlength]').forEach(field => {
      if (field.dataset.counted) return;
      field.dataset.counted = 'true';
      const count = document.createElement('small');
      const render = () => { count.textContent = `${field.value.length} / ${field.maxLength} caracteres`; };
      field.after(count); field.addEventListener('input', render); render();
    });
  }
  document.addEventListener('DOMContentLoaded', update);
  document.addEventListener('formset:added', update);
})();
