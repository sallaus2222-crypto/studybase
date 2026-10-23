(() => {
  const form = document.getElementById("form-marcacao");
  if (!form) return;

  const trechoId = form.querySelector("[name='trecho_id']");
  const trechoTexto = form.querySelector("[name='trecho_texto']");
  const preview = document.getElementById("trecho-selecionado");
  const salvar = document.getElementById("salvar-marcacao");

  document.querySelectorAll(".destaque-salvo").forEach((destaque) => {
    const secao = destaque.closest("[data-trecho-id]");
    const texto = destaque.dataset.texto;
    if (!secao || !texto) return;

    const walker = document.createTreeWalker(secao, NodeFilter.SHOW_TEXT);
    let no;
    while ((no = walker.nextNode())) {
      const inicio = no.nodeValue.indexOf(texto);
      if (inicio < 0) continue;
      const range = document.createRange();
      range.setStart(no, inicio);
      range.setEnd(no, inicio + texto.length);
      const marca = document.createElement("mark");
      marca.className = `texto-marcado cor-${destaque.dataset.cor}`;
      range.surroundContents(marca);
      break;
    }
  });

  if (window.location.hash.startsWith("#trecho-")) {
    const alvoInicial = document.querySelector(window.location.hash);
    if (alvoInicial) alvoInicial.classList.add("leitor-secao-ativa");
  }

  document.addEventListener("mouseup", () => {
    const selecao = window.getSelection();
    const texto = selecao ? selecao.toString().trim() : "";
    if (!texto || texto.length > 1000) return;

    const ancora = selecao.anchorNode;
    const elemento = ancora && (ancora.nodeType === Node.ELEMENT_NODE
      ? ancora
      : ancora.parentElement);
    const secao = elemento && elemento.closest("[data-trecho-id]");
    if (!secao) return;

    trechoId.value = secao.dataset.trechoId;
    trechoTexto.value = texto;
    preview.textContent = `“${texto}”`;
    salvar.disabled = false;
  });

  document.addEventListener("click", (evento) => {
    const link = evento.target.closest(".marcacao-trecho[href^='#trecho-']");
    if (!link) return;
    const alvo = document.querySelector(link.getAttribute("href"));
    if (!alvo) return;
    alvo.classList.add("leitor-secao-ativa");
    window.setTimeout(() => alvo.classList.remove("leitor-secao-ativa"), 1800);
  });
})();
