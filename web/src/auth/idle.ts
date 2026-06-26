// Logout por INATIVIDADE no cliente. O dono da regra é o BACKEND (o cookie de refresh é deslizante e
// morre em AUTH_IDLE_TIMEOUT_SECONDS sem renovar → o /refresh falha → logout); este watcher é só UX:
// desloga PROATIVAMENTE quando o usuário deixa o app aberto e parado, em vez de esperar a próxima
// chamada falhar. Robusto ao "sono" do device: compara timestamps (não confia só em setTimeout, que
// congela quando a aba dorme) e re-checa ao focar/voltar a aba; compartilha a última atividade entre
// abas via localStorage. IDLE_TIMEOUT_MS DEVE espelhar AUTH_IDLE_TIMEOUT_SECONDS do backend (6h).
export const IDLE_TIMEOUT_MS = 6 * 60 * 60 * 1000

const KEY = "cria:ultima-atividade"
// Eventos que contam como "usuário presente". passive: não atrapalham o scroll/touch.
const EVENTS = ["pointerdown", "keydown", "scroll", "wheel", "touchstart"] as const
const CHECK_MS = 60_000 // re-checa de minuto em minuto (e ao focar/exibir a aba)
const WRITE_THROTTLE_MS = 30_000 // scroll/wheel disparam em rajada; gravar 1x/30s basta p/ 6h

// Fallback em memória do módulo: se o localStorage falhar (modo privado/cota), NÃO cair em Date.now()
// no leitor (re-armaria a contagem a cada checagem → nunca expira). Este valor sustenta a janela.
let _memTs = Date.now()
let _ultimaEscrita = 0

function marcar(): void {
  const agora = Date.now()
  _memTs = agora
  if (agora - _ultimaEscrita < WRITE_THROTTLE_MS) return // throttle do I/O (e do evento 'storage')
  _ultimaEscrita = agora
  try {
    localStorage.setItem(KEY, String(agora))
  } catch {
    /* storage indisponível: _memTs (memória) sustenta a contagem; o backend ainda corta em 6h */
  }
}

function ultimaAtividade(): number {
  try {
    const v = Number(localStorage.getItem(KEY)) // outras abas também atualizam aqui
    if (v) return v
  } catch {
    /* cai no fallback de memória */
  }
  return _memTs
}

/** Dispara `onIdle` quando passam IDLE_TIMEOUT_MS sem atividade do usuário. Retorna o cleanup. */
export function watchIdle(onIdle: () => void): () => void {
  marcar() // a sessão começa "ativa" agora (login/boot)
  let parado = false
  const checar = (): void => {
    if (parado) return
    if (Date.now() - ultimaAtividade() >= IDLE_TIMEOUT_MS) {
      parado = true // dispara uma vez só
      onIdle()
    }
  }
  const aoInteragir = (): void => {
    if (!parado) marcar()
  }
  const aoVoltar = (): void => {
    // o device pode ter dormido (timers congelam) → re-checa na hora ao focar/exibir
    if (document.visibilityState === "visible") checar()
  }
  for (const ev of EVENTS) window.addEventListener(ev, aoInteragir, { passive: true })
  window.addEventListener("focus", aoVoltar)
  document.addEventListener("visibilitychange", aoVoltar)
  const timer = window.setInterval(checar, CHECK_MS)
  return () => {
    parado = true
    window.clearInterval(timer)
    for (const ev of EVENTS) window.removeEventListener(ev, aoInteragir)
    window.removeEventListener("focus", aoVoltar)
    document.removeEventListener("visibilitychange", aoVoltar)
  }
}
