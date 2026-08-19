import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useQueueWebSocket } from "@/lib/hooks/useQueueWebSocket";
import { useQueueStore } from "@/lib/stores/queueStore";

/** WebSocket de mentira: guarda todos los que se han abierto para poder
 *  comprobar cuántos quedan VIVOS y con qué filtro se abrió cada uno. */
class SocketFalso {
  static abiertos: SocketFalso[] = [];
  static get vivos(): SocketFalso[] {
    return SocketFalso.abiertos.filter((s) => s.readyState === 1);
  }

  /** El único que debería quedar vivo. Falla claro si hay 0 o 2 — que es
   *  justo el fallo que persigue este fichero. */
  static get unico(): SocketFalso {
    const vivos = SocketFalso.vivos;
    if (vivos.length !== 1) {
      throw new Error(`se esperaba 1 socket vivo, hay ${vivos.length}`);
    }
    return vivos[0]!;
  }

  static OPEN = 1;
  static CLOSED = 3;
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    SocketFalso.abiertos.push(this);
  }

  /** El `de` con el que se pidió esta conexión ("" = la mía). */
  get filtro(): string {
    return new URL(this.url, "http://x").searchParams.get("de") ?? "";
  }

  send() {}

  close() {
    // Como en un navegador: el cierre NO es inmediato, `onclose` llega después.
    this.readyState = 3;
    setTimeout(() => this.onclose?.(), 0);
  }

  /** Simula el snapshot que manda el servidor al conectar. */
  recibirSnapshot(jobs: unknown[]) {
    this.onmessage?.({
      data: JSON.stringify({
        type: "snapshot",
        data: { jobs, viendo: this.filtro || "ness", es_admin: true, otros: {} },
      }),
    });
  }
}

function job(id: string, quien: string) {
  return {
    job_id: id,
    mode: "nicho_pov_bof_largo_video",
    title: `de ${quien}`,
    status: "pending",
    progress_percent: 0,
    current_step: "",
    elapsed_seconds: 0,
    created_at: 1,
    started_at: null,
    finished_at: null,
    enqueued_by: quien,
    error: null,
    result_path: null,
  };
}

describe("el socket de la cola al cambiar de 'Viendo'", () => {
  beforeEach(() => {
    SocketFalso.abiertos = [];
    vi.stubGlobal("WebSocket", SocketFalso as unknown as typeof WebSocket);
    useQueueStore.getState().reset();
    useQueueStore.setState({ verDe: "" });
  });

  it("no deja vivo el socket de la cola anterior", async () => {
    renderHook(() => useQueueWebSocket());
    await waitFor(() => expect(SocketFalso.vivos).toHaveLength(1));
    expect(SocketFalso.unico.filtro).toBe("");

    // El admin pulsa "Ana".
    act(() => useQueueStore.getState().setVerDe("ana"));

    await waitFor(() => expect(SocketFalso.unico.filtro).toBe("ana"));
  });

  it("el socket viejo, al despedirse, no reabre la cola anterior", async () => {
    renderHook(() => useQueueWebSocket());
    await waitFor(() => expect(SocketFalso.vivos).toHaveLength(1));
    const viejo = SocketFalso.unico;

    act(() => useQueueStore.getState().setVerDe("ana"));
    await waitFor(() => expect(SocketFalso.unico.filtro).toBe("ana"));

    // Su `onclose` llega AHORA, con el socket nuevo ya abierto. Antes esto
    // programaba una reconexión con el filtro de antes y acababas con dos
    // sockets peleándose: se veía un par de recargas y ganaba el viejo.
    act(() => viejo.onclose?.());
    await new Promise((r) => setTimeout(r, 50));

    expect(SocketFalso.unico.filtro).toBe("ana");
  });

  it("un snapshot del socket viejo ya no pisa lo que se está viendo", async () => {
    renderHook(() => useQueueWebSocket());
    await waitFor(() => expect(SocketFalso.vivos).toHaveLength(1));
    const viejo = SocketFalso.unico;

    act(() => useQueueStore.getState().setVerDe("ana"));
    await waitFor(() => expect(SocketFalso.unico.filtro).toBe("ana"));
    const nuevo = SocketFalso.unico;

    act(() => nuevo.recibirSnapshot([job("1", "ana")]));
    // El viejo contesta tarde con LO MÍO: tiene que caer en saco roto.
    act(() => viejo.recibirSnapshot([job("9", "ness")]));

    const activos = Object.values(useQueueStore.getState().active);
    expect(activos.map((j) => j.enqueued_by)).toEqual(["ana"]);
  });

  it("al cambiar de cola se vacía lo anterior en vez de dejarlo en pantalla", async () => {
    renderHook(() => useQueueWebSocket());
    await waitFor(() => expect(SocketFalso.vivos).toHaveLength(1));
    act(() => SocketFalso.unico.recibirSnapshot([job("9", "ness")]));
    expect(Object.keys(useQueueStore.getState().active)).toHaveLength(1);

    act(() => useQueueStore.getState().setVerDe("ana"));
    expect(Object.keys(useQueueStore.getState().active)).toHaveLength(0);
  });
});
