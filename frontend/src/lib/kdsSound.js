import { useCallback, useEffect, useRef, useState } from 'react';

// Sons do KDS com Web Audio API (sem arquivos externos).
// O navegador só libera áudio depois de um clique: por isso o botão "Ativar som".

const STORAGE_KEY = 'gestorresto_kds_sound';
const OBS_REPEAT_MS = 10000;
const CANCEL_REPEAT_MS = 10000;
const LATE_REPEAT_MS = 3 * 60 * 1000;

let ctx = null;

function getCtx() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  return ctx;
}

function readSaved() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch (e) {
    return false;
  }
}

function save(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0');
  } catch (e) {
    // sem armazenamento: o estado vale só nesta aba
  }
}

function tone(freqStart, freqEnd, start, duration, { type = 'sine', volume = 0.3 } = {}) {
  const c = getCtx();
  if (!c || c.state !== 'running') return;
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

// Pedido novo: "plim" curto (duas notas agudas, sobe).
export function playNewOrder() {
  tone(1320, 1320, 0, 0.12, { volume: 0.25 });
  tone(1760, 1760, 0.1, 0.25, { volume: 0.2 });
}

// Observação nova: dois bipes rápidos.
export function playObservation() {
  tone(950, 950, 0, 0.09, { type: 'square', volume: 0.15 });
  tone(950, 950, 0.16, 0.09, { type: 'square', volume: 0.15 });
}

// Cancelado: tom grave descendo.
export function playCancelled() {
  tone(420, 140, 0, 0.9, { type: 'triangle', volume: 0.35 });
}

// Atrasado: três toques médios, insistentes.
export function playLate() {
  [0, 0.22, 0.44].forEach(t => tone(660, 660, t, 0.15, { type: 'sawtooth', volume: 0.12 }));
}

export function useKdsSound() {
  const [enabled, setEnabled] = useState(readSaved);
  const [running, setRunning] = useState(false);

  const enable = useCallback(async () => {
    const c = getCtx();
    if (!c) return;
    try {
      await c.resume();
    } catch (e) {
      // ignora
    }
    save(true);
    setEnabled(true);
    setRunning(c.state === 'running');
    playNewOrder();
  }, []);

  const disable = useCallback(() => {
    save(false);
    setEnabled(false);
  }, []);

  // Som salvo como ativo: libera o áudio no primeiro toque/tecla da tela.
  useEffect(() => {
    if (!enabled) return undefined;
    const c = getCtx();
    if (!c) return undefined;
    if (c.state === 'running') {
      setRunning(true);
      return undefined;
    }
    const unlock = () => {
      c.resume().then(() => setRunning(c.state === 'running')).catch(() => {});
    };
    window.addEventListener('pointerdown', unlock, { once: true });
    window.addEventListener('keydown', unlock, { once: true });
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
    };
  }, [enabled]);

  return { enabled, running: enabled && running, enable, disable };
}

/**
 * Regras de som do KDS (iguais em Cozinha, Bar e Churrasqueira).
 *
 * ready:       false enquanto a tela carrega (não toca o "plim" da carga inicial)
 * newOrderIds:  ids dos pedidos com itens novos visíveis nesta tela
 * pendingObsIds: ids das observações ainda sem "Ciente" nesta tela
 * pendingCancelIds: ids dos pedidos cancelados ainda sem "Ciente" nesta tela
 * lateOrderIds: ids dos pedidos atrasados visíveis nesta tela
 */
export function useKdsAlerts({ ready = true, soundOn, newOrderIds, pendingObsIds, pendingCancelIds, lateOrderIds }) {
  const data = useRef({});
  data.current = { soundOn, newOrderIds, pendingObsIds, pendingCancelIds, lateOrderIds };

  const seen = useRef({ orders: null, obs: new Set(), cancels: new Set(), late: new Set() });
  const last = useRef({ obs: 0, cancel: 0, late: 0 });

  // Pedido novo: toca uma vez quando aparece um id que ainda não existia.
  const orderKey = (newOrderIds || []).join('|');
  useEffect(() => {
    if (!ready) return; // a primeira carga da tela não toca
    const ids = new Set(newOrderIds || []);
    const prev = seen.current.orders;
    if (prev && soundOn && [...ids].some(id => !prev.has(id))) {
      playNewOrder();
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
      if (!d.soundOn) return;

      // Um som por vez, do mais grave para o mais leve.
      if (cancels.size && (newCancel || now - last.current.cancel >= CANCEL_REPEAT_MS)) {
        playCancelled();
        last.current.cancel = now;
        return;
      }
      if (obs.size && (newObs || now - last.current.obs >= OBS_REPEAT_MS)) {
        playObservation();
        last.current.obs = now;
        return;
      }
      if (late.size && (newLate || now - last.current.late >= LATE_REPEAT_MS)) {
        playLate();
        last.current.late = now;
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
}
