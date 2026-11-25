import { useCallback, useEffect, useRef, useState } from 'react';

// Sons do KDS com Web Audio API (sem arquivos externos).
//
// O som toca SOZINHO, como sempre tocou. Só quando o navegador bloqueia a
// reprodução automática (política de autoplay) é que a tela mostra o aviso
// "Ativar som": um toque na tela libera o áudio e o aviso some.
// No kiosk da cozinha, abra o Chromium com --autoplay-policy=no-user-gesture-required
// (veja o README) para o bloqueio nunca acontecer.

const OBS_REPEAT_MS = 10000;
const CANCEL_REPEAT_MS = 10000;
const LATE_REPEAT_MS = 3 * 60 * 1000;
const RESUME_TIMEOUT_MS = 300;

let ctx = null;

function getCtx() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try {
      ctx = new AC();
    } catch (e) {
      return null;
    }
  }
  return ctx;
}

function blockedError() {
  try {
    return new DOMException('Reprodução automática bloqueada pelo navegador', 'NotAllowedError');
  } catch (e) {
    const err = new Error('Reprodução automática bloqueada pelo navegador');
    err.name = 'NotAllowedError';
    return err;
  }
}

// Libera o áudio. Com o autoplay bloqueado, resume() fica pendente até um
// toque do usuário: por isso o limite de tempo e a checagem do estado.
async function unlockAudio() {
  const c = getCtx();
  if (!c) throw new Error('Áudio não suportado neste navegador');
  if (c.state !== 'running') {
    await Promise.race([
      c.resume().catch(() => {}),
      new Promise(resolve => setTimeout(resolve, RESUME_TIMEOUT_MS)),
    ]);
  }
  if (c.state !== 'running') throw blockedError();
  return c;
}

function tone(c, freqStart, freqEnd, start, duration, { type = 'sine', volume = 0.3 } = {}) {
  const t0 = c.currentTime + start;
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freqStart, t0);
  if (freqEnd !== freqStart) {
    osc.frequency.exponentialRampToValueAtTime(freqEnd, t0 + duration);
  }
  gain.gain.setValueAtTime(0.0001, t0);
  gain.gain.exponentialRampToValueAtTime(volume, t0 + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
  osc.connect(gain);
  gain.connect(c.destination);
  osc.start(t0);
  osc.stop(t0 + duration + 0.02);
}

// Cada som é bem diferente dos outros para a equipe reconhecer sem olhar a tela.
export const SOUNDS = {
  // Pedido novo: "plim" curto (duas notas agudas, subindo).
  newOrder: c => {
    tone(c, 1320, 1320, 0, 0.12, { volume: 0.25 });
    tone(c, 1760, 1760, 0.1, 0.25, { volume: 0.2 });
  },
  // Atrasado: três toques médios e ásperos, insistentes.
  late: c => {
    [0, 0.22, 0.44].forEach(t => tone(c, 660, 660, t, 0.15, { type: 'sawtooth', volume: 0.12 }));
  },
  // Cancelado: tom grave descendo, longo.
  cancelled: c => {
    tone(c, 420, 140, 0, 0.9, { type: 'triangle', volume: 0.35 });
  },
  // Observação nova: dois bipes rápidos.
  observation: c => {
    tone(c, 950, 950, 0, 0.09, { type: 'square', volume: 0.15 });
    tone(c, 950, 950, 0.16, 0.09, { type: 'square', volume: 0.15 });
  },
};

/**
 * Toca um dos SOUNDS. Rejeita com NotAllowedError quando o navegador bloqueia
 * a reprodução automática (equivalente ao erro do play() de um <audio>).
 */
export async function play(kind) {
  const c = await unlockAudio();
  const sound = SOUNDS[kind];
  if (sound) sound(c);
}

export function useKdsSound() {
  // null = ainda testando; true = navegador bloqueou; false = som liberado.
  const [blocked, setBlocked] = useState(null);

  const playSafe = useCallback(async kind => {
    try {
      await play(kind);
      setBlocked(false);
      return true;
    } catch (e) {
      if (e && e.name === 'NotAllowedError') setBlocked(true);
      else console.log('Áudio não suportado:', e?.message || e);
      return false;
    }
  }, []);

  // Clique no aviso "Ativar som": libera e toca o som de pedido novo como teste.
  const enable = useCallback(() => playSafe('newOrder'), [playSafe]);

  // Ao abrir a tela já descobre se o navegador bloqueia (o aviso aparece antes
  // do primeiro pedido, não depois de um pedido perdido).
  useEffect(() => {
    let alive = true;
    unlockAudio()
      .then(() => alive && setBlocked(false))
      .catch(e => alive && e?.name === 'NotAllowedError' && setBlocked(true));
    return () => {
      alive = false;
    };
  }, []);

  // Bloqueado: qualquer toque ou tecla na tela já libera o áudio.
  useEffect(() => {
    if (!blocked) return undefined;
    const retry = () => {
      unlockAudio().then(() => setBlocked(false)).catch(() => {});
    };
    window.addEventListener('pointerdown', retry);
    window.addEventListener('keydown', retry);
    return () => {
      window.removeEventListener('pointerdown', retry);
      window.removeEventListener('keydown', retry);
    };
  }, [blocked]);

  return { blocked: blocked === true, play: playSafe, enable };
}

/**
 * Regras de som do KDS (iguais em Cozinha, Bar e Churrasqueira).
 *
 * sound:            retorno de useKdsSound()
 * ready:            false enquanto a tela carrega (não toca o "plim" da carga inicial)
 * newOrderIds:      ids dos pedidos com itens novos visíveis nesta tela
 * pendingObsIds:    ids das observações ainda sem "Ciente" nesta tela
 * pendingCancelIds: ids dos pedidos cancelados ainda sem "Ciente" nesta tela
 * lateOrderIds:     ids dos pedidos atrasados visíveis nesta tela
 */
export function useKdsAlerts({ sound, ready = true, newOrderIds, pendingObsIds, pendingCancelIds, lateOrderIds }) {
  const data = useRef({});
  data.current = { sound, pendingObsIds, pendingCancelIds, lateOrderIds };

  const seen = useRef({ orders: null, obs: new Set(), cancels: new Set(), late: new Set() });
  const last = useRef({ obs: 0, cancel: 0, late: 0 });

  // Pedido novo: toca uma vez quando aparece um id que ainda não existia.
  const orderKey = (newOrderIds || []).join('|');
  useEffect(() => {
    if (!ready) return; // a primeira carga da tela não toca
    const ids = new Set(newOrderIds || []);
    const prev = seen.current.orders;
    if (prev && [...ids].some(id => !prev.has(id))) {
      data.current.sound.play('newOrder');
    }
    seen.current.orders = ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderKey, ready]);

  useEffect(() => {
    const tick = () => {
      const d = data.current;
      const now = Date.now();
      const obs = new Set(d.pendingObsIds || []);
      const cancels = new Set(d.pendingCancelIds || []);
      const late = new Set(d.lateOrderIds || []);
      const newObs = [...obs].some(id => !seen.current.obs.has(id));
      const newCancel = [...cancels].some(id => !seen.current.cancels.has(id));
      const newLate = [...late].some(id => !seen.current.late.has(id));
      seen.current.obs = obs;
      seen.current.cancels = cancels;
      seen.current.late = late;
      if (d.sound.blocked) return; // o aviso "Ativar som" já está na tela

      // Um som por vez, do mais grave para o mais leve.
      if (cancels.size && (newCancel || now - last.current.cancel >= CANCEL_REPEAT_MS)) {
        d.sound.play('cancelled');
        last.current.cancel = now;
        return;
      }
      if (obs.size && (newObs || now - last.current.obs >= OBS_REPEAT_MS)) {
        d.sound.play('observation');
        last.current.obs = now;
        return;
      }
      if (late.size && (newLate || now - last.current.late >= LATE_REPEAT_MS)) {
        d.sound.play('late');
        last.current.late = now;
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
}
