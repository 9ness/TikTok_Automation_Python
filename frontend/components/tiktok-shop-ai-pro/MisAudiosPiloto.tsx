"use client";

import { Loader2, Mic, Square, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  audioPilotoUrl,
  useAudiosPiloto,
  useBorrarAudioPiloto,
  useSubirAudioPiloto,
  type GuionAudio,
} from "@/lib/queries/cuentaPiloto";

const SEXOS = ["mujer", "hombre"] as const;

/** Los diez guiones grabados con la voz del propio operador.
 *
 *  En la Cuenta Piloto cada cuenta es de una persona distinta, así que la voz
 *  tiene que ser la suya y no la del banco compartido del curso.
 *
 *  Se graba aquí mismo con el micro del móvil. Si el navegador no deja (pasa en
 *  la app instalada si se le negó el permiso al micro), queda el botón de subir
 *  un fichero, que abre la grabadora del teléfono — el resultado es el mismo,
 *  porque el servidor convierte a mp3 venga como venga.
 */
export function MisAudiosPiloto({ sexoInicial = "mujer" }: { sexoInicial?: string }) {
  const [sexo, setSexo] = useState<string>(sexoInicial);
  const audios = useAudiosPiloto(sexo);
  const items = audios.data ?? [];
  const hechos = items.filter((g) => g.grabado).length;

  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex items-baseline gap-2">
        <p className="text-sm font-semibold">🎙️ Mis audios</p>
        <p className="text-[10px] text-muted-foreground">
          tu voz, no la del banco
        </p>
        <span
          className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold ${
            hechos === items.length && items.length > 0
              ? "bg-emerald-500/15 text-emerald-500"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {hechos}/{items.length}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {SEXOS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSexo(s)}
            className={`rounded-lg border px-2 py-1.5 text-[11px] transition ${
              sexo === s
                ? "border-sky-500 bg-sky-500/10 font-semibold text-sky-500"
                : "border-border/60 text-muted-foreground"
            }`}
          >
            {s === "mujer" ? "👩 Voz de mujer" : "👨 Voz de hombre"}
          </button>
        ))}
      </div>

      <p className="text-[10px] leading-relaxed text-muted-foreground">
        Lee el texto en voz alta y graba. Los cinco primeros son los de siempre;
        los de <b>plazos</b> se usan en los productos que pasan de 40 €. Mientras
        falte alguno, esos vídeos tiran del banco compartido.
      </p>

      {audios.isLoading && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
        </p>
      )}

      {(["normal", "plazos"] as const).map((tipo) => (
        <div key={tipo} className="space-y-1.5">
          <p className="text-[10px] font-semibold text-muted-foreground">
            {tipo === "normal" ? "Guiones normales" : "Guiones de plazos"}
          </p>
          {items
            .filter((g) => g.tipo === tipo)
            .map((g) => (
              <FilaGuion key={`${g.tipo}${g.n}`} sexo={sexo} guion={g} />
            ))}
        </div>
      ))}
    </section>
  );
}

function FilaGuion({ sexo, guion }: { sexo: string; guion: GuionAudio }) {
  const subir = useSubirAudioPiloto();
  const borrar = useBorrarAudioPiloto();
  const [grabando, setGrabando] = useState(false);
  const [segundos, setSegundos] = useState(0);
  const grabadora = useRef<MediaRecorder | null>(null);
  const trozos = useRef<Blob[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Cronómetro mientras se graba: sin él no se sabe si el micro está cogiendo
  // algo hasta que se para y se escucha.
  useEffect(() => {
    if (!grabando) return;
    const id = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [grabando]);

  // Si se sale de la pantalla con la grabación en marcha, hay que soltar el
  // micro: si no, el móvil se queda con el punto rojo encendido.
  useEffect(
    () => () => {
      grabadora.current?.stream.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  async function empezar() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      toast.error(
        "Este navegador no deja grabar. Usa el botón de subir y graba con la grabadora del móvil.",
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      trozos.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) trozos.current.push(e.data);
      };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(trozos.current, { type: rec.mimeType || "audio/webm" });
        if (blob.size < 1024) {
          toast.error("No se ha grabado nada. ¿Le has dado permiso al micro?");
          return;
        }
        subir.mutate(
          { sexo, tipo: guion.tipo, n: guion.n, blob },
          {
            onSuccess: () => toast.success("Audio guardado"),
            onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
          },
        );
      };
      grabadora.current = rec;
      setSegundos(0);
      setGrabando(true);
      rec.start();
    } catch {
      toast.error(
        "No se pudo abrir el micro. Dale permiso al navegador, o graba con la grabadora del móvil y súbelo.",
      );
    }
  }

  function parar() {
    grabadora.current?.stop();
    grabadora.current = null;
    setGrabando(false);
  }

  const ocupado = subir.isPending || borrar.isPending;

  return (
    <div
      className={`space-y-1.5 rounded-lg border p-2 ${
        guion.grabado ? "border-emerald-500/40 bg-emerald-500/5" : "border-border/60"
      }`}
    >
      <p className="flex items-baseline gap-1.5 text-[10px] font-semibold">
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-muted-foreground">
          {guion.n}
        </span>
        {guion.grabado ? (
          <span className="text-emerald-500">✅ grabado · {guion.segundos}s</span>
        ) : (
          <span className="text-muted-foreground">sin grabar</span>
        )}
      </p>
      {/* El texto va entero y legible: la pantalla es para leerlo en voz alta
          mientras se graba, no para identificar el guion. */}
      <p className="text-[11px] leading-relaxed">{guion.texto}</p>

      {guion.grabado && (
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio
          controls
          preload="none"
          src={audioPilotoUrl(sexo, guion.tipo, guion.n, guion.grabado_at)}
          className="h-8 w-full"
        />
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        {grabando ? (
          <button
            type="button"
            onClick={parar}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-red-500 px-2 py-1.5 text-[11px] font-semibold text-white"
          >
            <Square className="h-3.5 w-3.5" /> Parar ({segundos}s)
          </button>
        ) : (
          <button
            type="button"
            disabled={ocupado}
            onClick={() => void empezar()}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-sky-500 px-2 py-1.5 text-[11px] font-semibold text-white transition hover:bg-sky-600 disabled:opacity-50"
          >
            {subir.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Guardando…
              </>
            ) : (
              <>
                <Mic className="h-3.5 w-3.5" /> {guion.grabado ? "Regrabar" : "Grabar"}
              </>
            )}
          </button>
        )}

        {/* Salida de emergencia: si el navegador no deja usar el micro, esto
            abre la grabadora del móvil y el audio entra igual. */}
        <label
          className="flex cursor-pointer items-center gap-1 rounded-md border border-border/60 px-2 py-1.5 text-[10px] text-muted-foreground transition hover:text-foreground"
          title="Subir un audio grabado con la grabadora del móvil"
        >
          <Upload className="h-3 w-3" />
          <input
            ref={inputRef}
            type="file"
            accept="audio/*"
            className="hidden"
            disabled={ocupado || grabando}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              subir.mutate(
                { sexo, tipo: guion.tipo, n: guion.n, blob: f, nombre: f.name },
                {
                  onSuccess: () => toast.success("Audio guardado"),
                  onError: (err) =>
                    toast.error(err instanceof ApiError ? err.message : String(err)),
                },
              );
            }}
          />
        </label>

        {guion.grabado && (
          <button
            type="button"
            disabled={ocupado || grabando}
            onClick={() =>
              borrar.mutate(
                { sexo, tipo: guion.tipo, n: guion.n },
                {
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : String(e)),
                },
              )
            }
            className="rounded-md border border-border/60 p-1.5 text-muted-foreground transition hover:text-red-500"
            title="Borrar la grabación"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}
