document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("searchForm");
  const btn = document.getElementById("buscarBtn");
  const periodoSelect = document.getElementById("periodoSelect");
  const metodoSelect = document.getElementById("metodoSelect");
  const infoDiv = document.getElementById("info");
  const resultDiv = document.getElementById("resultado");
  const topNewsRail = document.getElementById("topNewsRail");
  const currentDate = document.getElementById("currentDate");
  const endpoint = document.body.dataset.endpoint;

  if (!form || !btn || !periodoSelect || !metodoSelect || !infoDiv || !resultDiv || !endpoint) {
    return;
  }

  const INITIAL_VISIBLE_NEWS = 6;
  let avisoAtual = "";
  let noticiasAtuais = [];
  let visibleNewsCount = INITIAL_VISIBLE_NEWS;

  const createNode = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const formatCurrentDate = () => {
    if (!currentDate) return;
    currentDate.dateTime = new Date().toISOString();
    currentDate.textContent = new Intl.DateTimeFormat("pt-BR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    }).format(new Date());
  };

  const setInfo = ({ tipo, periodo, metodo, quantidade, aviso }) => {
    infoDiv.replaceChildren();
    avisoAtual = aviso || "";

    [tipo, periodo, `Método: ${metodo}`, `${quantidade} resultado${quantidade === 1 ? "" : "s"}`]
      .forEach((text) => infoDiv.appendChild(createNode("span", "status-chip", text)));

    if (avisoAtual) {
      infoDiv.appendChild(createNode("span", "status-chip status-warning", avisoAtual));
    }
  };

  const getRelevanceTier = (relevancia = 0) => {
    if (relevancia >= 6) return "high";
    if (relevancia >= 3) return "medium";
    return "low";
  };

  const getRelevanceLabel = (tier) => {
    if (tier === "high") return "Alta";
    if (tier === "medium") return "Média";
    return "Baixa";
  };

  const renderCard = (noticia, variant = "feed") => {
    const tier = getRelevanceTier(Number(noticia.relevancia) || 0);
    const card = createNode("article", `card news-card ${variant}-card relevance-${tier}`);

    const header = createNode("div", "card-header");
    header.appendChild(createNode("span", "card-date", noticia.data || "Sem data"));
    header.appendChild(createNode("span", "relevance-badge", `${getRelevanceLabel(tier)} · ${noticia.relevancia ?? 0}`));

    const title = createNode("h3", "card-title", noticia.titulo || "Título não informado");
    const source = createNode("p", "card-source", noticia.fonte || "Fonte não informada");

    const link = createNode("a", "card-link", "Ler matéria completa");
    link.href = noticia.link || "#";
    link.target = "_blank";
    link.rel = "noopener noreferrer";

    card.append(header, title, source, link);
    return card;
  };

  const renderWeeklyGroup = (noticias, hidden = false) => {
    const group = createNode("div", "weekly-group");
    if (hidden) group.setAttribute("aria-hidden", "true");
    noticias.forEach((noticia) => group.appendChild(renderCard(noticia, "rail")));
    return group;
  };

  const renderTopRail = (noticias) => {
    if (!topNewsRail) return;

    topNewsRail.replaceChildren();
    if (!noticias.length) {
      topNewsRail.appendChild(createNode("div", "weekly-empty", "Nenhuma notícia encontrada para a faixa semanal."));
      return;
    }

    const track = createNode("div", "weekly-track");
    track.style.setProperty("--weekly-duration", `${Math.max(28, noticias.length * 7)}s`);
    track.appendChild(renderWeeklyGroup(noticias));
    track.appendChild(renderWeeklyGroup(noticias, true));
    topNewsRail.appendChild(track);
  };

  const renderTopRailLoading = () => {
    if (!topNewsRail) return;
    topNewsRail.replaceChildren(createNode("div", "weekly-empty", "Carregando notícias da semana..."));
  };

  const getFeaturedNews = (noticias) => [...noticias]
    .sort((a, b) => (Number(b.relevancia) || 0) - (Number(a.relevancia) || 0))
    .slice(0, Math.min(3, noticias.length));

  const renderFeatured = (noticias) => {
    const section = createNode("section", "hud-section featured-section");
    section.setAttribute("aria-labelledby", "destaquesTitulo");

    const header = createNode("div", "hud-heading");
    const copy = createNode("div");
    copy.appendChild(createNode("span", "eyebrow", "Destaques"));
    copy.appendChild(createNode("h3", "", "Notícias com maior relevância"));
    header.appendChild(copy);
    header.querySelector("h3").id = "destaquesTitulo";

    const grid = createNode("div", "featured-grid");
    getFeaturedNews(noticias).forEach((noticia) => grid.appendChild(renderCard(noticia, "featured")));
    section.append(header, grid);
    return section;
  };

  const renderFeedList = () => {
    const section = createNode("section", "hud-section feed-section");
    section.setAttribute("aria-labelledby", "feedTitulo");

    const header = createNode("div", "hud-heading");
    const copy = createNode("div");
    copy.appendChild(createNode("span", "eyebrow", "Feed principal"));
    copy.appendChild(createNode("h3", "", "Últimas notícias encontradas"));
    header.appendChild(copy);
    header.appendChild(createNode("span", "hud-count", `${Math.min(visibleNewsCount, noticiasAtuais.length)} de ${noticiasAtuais.length}`));
    header.querySelector("h3").id = "feedTitulo";

    const grid = createNode("div", "feed-grid");
    noticiasAtuais.slice(0, visibleNewsCount).forEach((noticia) => grid.appendChild(renderCard(noticia, "feed")));

    section.append(header, grid);

    if (noticiasAtuais.length > INITIAL_VISIBLE_NEWS) {
      const actions = createNode("div", "feed-actions");
      const button = createNode("button", "btn-secondary", visibleNewsCount >= noticiasAtuais.length ? "Todas as notícias visíveis" : "Ver mais");
      button.type = "button";
      button.disabled = visibleNewsCount >= noticiasAtuais.length;
      button.addEventListener("click", () => {
        visibleNewsCount = noticiasAtuais.length;
        renderResults();
      });
      actions.appendChild(button);
      section.appendChild(actions);
    }

    return section;
  };

  const renderResults = () => {
    resultDiv.className = "results-hud";
    resultDiv.replaceChildren(renderFeatured(noticiasAtuais), renderFeedList());
  };

  const showLoading = () => {
    infoDiv.textContent = "Buscando notícias...";
    renderTopRailLoading();
    resultDiv.className = "grid loading-grid";
    resultDiv.replaceChildren();

    for (let i = 0; i < 6; i += 1) {
      const skeleton = createNode("div", "card skeleton-card");
      skeleton.appendChild(createNode("span", "skeleton-line short"));
      skeleton.appendChild(createNode("span", "skeleton-line title"));
      skeleton.appendChild(createNode("span", "skeleton-line"));
      skeleton.appendChild(createNode("span", "skeleton-line tiny"));
      resultDiv.appendChild(skeleton);
    }
  };

  const showEmpty = () => {
    noticiasAtuais = [];
    renderTopRail([]);
    resultDiv.className = "results-hud";
    const empty = createNode("div", "empty-state");
    empty.appendChild(createNode("span", "eyebrow", avisoAtual ? "Motor indisponível" : "Sem resultados"));
    empty.appendChild(createNode("h3", "", avisoAtual || "Nenhuma notícia passou pelos filtros atuais."));
    empty.appendChild(createNode("p", "", "Tente ampliar o período ou alternar entre Google News, RSS Direto e Bing News."));
    resultDiv.replaceChildren(empty);
  };

  const buscarNoticias = async () => {
    const dias = Number.parseInt(periodoSelect.value, 10);
    const metodo = metodoSelect.value;
    const url = `${endpoint}?dias=${encodeURIComponent(dias)}&metodo=${encodeURIComponent(metodo)}`;

    btn.disabled = true;
    btn.querySelector("span").textContent = "Pesquisando";
    showLoading();

    try {
      const resp = await fetch(url, { headers: { Accept: "application/json" } });
      if (!resp.ok) throw new Error(`Erro HTTP ${resp.status}`);

      const data = await resp.json();
      setInfo(data);

      noticiasAtuais = Array.isArray(data.noticias) ? data.noticias : [];
      visibleNewsCount = Math.min(INITIAL_VISIBLE_NEWS, noticiasAtuais.length);

      if (!noticiasAtuais.length) {
        showEmpty();
        return;
      }

      renderTopRail(noticiasAtuais);
      renderResults();
    } catch (error) {
      infoDiv.textContent = "Erro ao buscar notícias.";
      resultDiv.className = "results-hud";
      resultDiv.replaceChildren();
      const empty = createNode("div", "empty-state error-state");
      empty.appendChild(createNode("span", "eyebrow", "Falha na consulta"));
      empty.appendChild(createNode("h3", "", "Não foi possível carregar os resultados agora."));
      empty.appendChild(createNode("p", "", "Verifique a conexão do backend e tente novamente."));
      resultDiv.appendChild(empty);
    } finally {
      btn.disabled = false;
      btn.querySelector("span").textContent = "Pesquisar";
    }
  };

  formatCurrentDate();
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    buscarNoticias();
  });

  setTimeout(() => {
    buscarNoticias();
  }, 0);
});
