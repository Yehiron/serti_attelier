(() => {
  const dataElement = document.getElementById('msg-data');
  if (!dataElement) return;
  const data = JSON.parse(dataElement.textContent);
  const input = document.getElementById('msg-reply');
  const whatsapp = document.getElementById('msg-whatsapp');
  const email = document.getElementById('msg-email');
  const offer = document.getElementById('msg-offer');
  const piece = data.piece || (data.locale === 'en' ? 'the piece' : 'la pieza');
  const templates = data.locale === 'en' ? {
    thanks: `Hello ${data.name}, thank you for writing to SERTI. We will be happy to help you.`,
    piece: `Hello ${data.name}, thank you for your interest in ${piece}. We will check its availability for you.`,
    appointment: `Hello ${data.name}, thank you for writing. We would be delighted to arrange an appointment at the atelier.`,
    custom: `Hello ${data.name}, thank you for thinking of SERTI for your custom piece. Tell us more about your idea.`,
  } : {
    thanks: `Hola ${data.name}, gracias por escribir a SERTI. Será un gusto ayudarte.`,
    piece: `Hola ${data.name}, gracias por tu interés en ${piece}. Revisaremos su disponibilidad para ti.`,
    appointment: `Hola ${data.name}, gracias por escribir. Será un gusto agendar una cita en el atelier.`,
    custom: `Hola ${data.name}, gracias por pensar en SERTI para tu pieza personalizada. Cuéntanos más sobre tu idea.`,
  };
  function update() {
    if (data.phone) whatsapp.href = `https://wa.me/${data.phone}?text=${encodeURIComponent(input.value)}`;
    email.href = `mailto:${encodeURIComponent(data.email)}?subject=${encodeURIComponent('SERTI · ' + data.topic)}&body=${encodeURIComponent(input.value)}`;
  }
  document.querySelectorAll('[data-template]').forEach(button => button.addEventListener('click', () => {
    input.value = templates[button.dataset.template];
    update();
  }));
  input.addEventListener('input', update);
  [whatsapp, email].forEach(link => link.addEventListener('click', event => {
    if (link.getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
    offer.hidden = false;
  }));
  update();
})();
