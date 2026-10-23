document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-bloquear-colagem]").forEach((form) => {
    const impedirColagem = (evento) => {
      const campo = evento.target.closest("textarea, input:not([type='hidden']):not([type='submit'])");
      if (!campo || !form.contains(campo)) return;

      evento.preventDefault();
      const mensagem = form.querySelector(".mensagem-bloqueio-colagem");
      if (mensagem) mensagem.hidden = false;
    };

    form.addEventListener("paste", impedirColagem);
    form.addEventListener("drop", impedirColagem);
  });
});
