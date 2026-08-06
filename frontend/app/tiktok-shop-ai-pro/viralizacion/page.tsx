"use client";

import { useEffect, useState } from "react";
import {
  ChevronDown,
  ExternalLink,
  Loader2,
  Palette,
  Rocket,
  Scissors,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  useAudios,
  useCuentasEjemplo,
  useGuardarCuentasEjemplo,
  type CuentaEjemplo,
  useCarpetas,
  useEstilos,
  useGenerateViralizacion,
  usePonentes,
  useRoundPlan,
  useCortarClips,
  useDescartarPropuesta,
  usePropuestasClips,
  useSubirAudioLargo,
  type AudioItem,
} from "@/lib/queries/viralizacion";
import type { PonenteInfo } from "@/lib/types/viralizacion";
import { useDrawerStore } from "@/lib/stores/drawerStore";

/** Cuentas de TikTok que ya siguen esta estrategia: sirven para mirar qué
 *  suben, con qué frecuencia y con qué hashtags. La lista es editable y vive
 *  en Redis — el operador va encontrando cuentas nuevas y no tiene sentido un
 *  despliegue por cada una. */
function CuentasEjemplo() {
  const [abierto, setAbierto] = useState(false);
  const [nueva, setNueva] = useState("");
  const cuentasQuery = useCuentasEjemplo();
  const guardar = useGuardarCuentasEjemplo();
  const cuentas = cuentasQuery.data ?? [];

  function aplicar(siguientes: CuentaEjemplo[]) {
    guardar.mutate(siguientes, {
      onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
    });
  }

  return (
    <section className="rounded-xl border border-border/60 bg-card">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs font-semibold sm:text-sm"
      >
        <Users className="h-4 w-4 shrink-0 text-amber-500" />
        <span className="flex-1">Cuentas de ejemplo</span>
        <span className="text-[11px] font-normal text-muted-foreground">
          {cuentas.length}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${
            abierto ? "rotate-180" : ""
          }`}
        />
      </button>
      {abierto && (
        <div className="space-y-2 border-t border-border/60 p-3 pt-2.5">
          <p className="text-[11px] text-muted-foreground">
            Cuentas con esta misma estrategia — mira qué prueban, qué suben y
            qué hashtags usan.
          </p>

          {cuentas.map((c) => (
            <div
              key={c.handle}
              className="flex items-center gap-2 rounded-lg border border-border/60 px-2.5 py-2"
            >
              <a
                href={`https://www.tiktok.com/${c.handle}`}
                target="_blank"
                rel="noreferrer"
                className="min-w-0 flex-1"
              >
                <p className="truncate text-xs font-medium">{c.handle}</p>
                {c.nota && (
                  <p className="truncate text-[10px] text-muted-foreground">
                    {c.nota}
                  </p>
                )}
              </a>
              <a
                href={`https://www.tiktok.com/${c.handle}`}
                target="_blank"
                rel="noreferrer"
                aria-label={`Abrir ${c.handle}`}
                className="shrink-0 text-muted-foreground transition hover:text-foreground"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
              <button
                type="button"
                aria-label={`Quitar ${c.handle}`}
                onClick={() => aplicar(cuentas.filter((x) => x.handle !== c.handle))}
                className="shrink-0 text-muted-foreground transition hover:text-destructive"
              >
                ×
              </button>
            </div>
          ))}
          {cuentas.length === 0 && !cuentasQuery.isLoading && (
            <p className="text-[11px] text-muted-foreground">Ninguna todavía.</p>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              const h = nueva.trim();
              if (!h) return;
              aplicar([...cuentas, { handle: h, nota: "" }]);
              setNueva("");
            }}
            className="flex gap-1.5"
          >
            {/* Acepta el @usuario o la URL entera pegada: al compartir desde
                la app sale la URL, y obligar a recortarla solo da errores. */}
            <input
              value={nueva}
              onChange={(e) => setNueva(e.target.value)}
              placeholder="@usuario o la URL de TikTok"
              className="min-w-0 flex-1 rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs"
            />
            <button
              type="submit"
              disabled={guardar.isPending || !nueva.trim()}
              className="rounded-md border border-border/60 px-3 py-1.5 text-xs font-medium transition hover:border-foreground/30 disabled:opacity-50"
            >
              Añadir
            </button>
          </form>
        </div>
      )}
    </section>
  );
}

/** mm:ss — es como el operador mira los audios (los elige por duración). */
function mmss(segundos: number): string {
  const s = Math.round(segundos);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Trocear una charla larga de YouTube en clips de ~1 minuto.
 *
 *  El operador encuentra charlas de 3-10 min del mismo ponente que empiezan
 *  distinto a lo que ya tiene. De ahí no sirve el audio entero: hay que saber
 *  dónde arranca cada idea con gancho propio y dónde cierra. Lo propone Gemini
 *  sobre la transcripción de Whisper y los cortes se ajustan a un silencio real.
 *
 *  Se REVISA antes de cortar: un clip que empieza a media frase no se nota
 *  hasta que el vídeo está montado y subido. */
function CortarAudioLargo({ ponentes }: { ponentes: PonenteInfo[] }) {
  const [abierto, setAbierto] = useState(false);
  const [ponente, setPonente] = useState("");
  const [file, setFile] = useState<File | null>(null);
  // Qué clips van marcados, por "<fichero>:<índice>". Todos marcados de
  // entrada: lo normal es querer los que propone y descartar alguno suelto.
  const [quitados, setQuitados] = useState<Set<string>>(new Set());

  const subir = useSubirAudioLargo();
  const cortar = useCortarClips();
  const descartar = useDescartarPropuesta();
  const propuestas = usePropuestasClips();
  const openQueue = useDrawerStore((s) => s.openQueue);

  const pendientes = propuestas.data ?? [];
  const elegido = ponente || ponentes[0]?.slug || "";

  function marcado(fichero: string, i: number) {
    return !quitados.has(`${fichero}:${i}`);
  }

  function alternar(fichero: string, i: number) {
    setQuitados((prev) => {
      const next = new Set(prev);
      const k = `${fichero}:${i}`;
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  function enviar() {
    if (!file || !elegido) return;
    subir.mutate(
      { ponente: elegido, file },
      {
        onSuccess: (r) => {
          toast.success(r.mensaje);
          setFile(null);
          openQueue();
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  return (
    <section className="rounded-xl border border-border/60 bg-card">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs font-semibold sm:text-sm"
      >
        <Scissors className="h-4 w-4 shrink-0 text-amber-500" />
        <span className="flex-1">Cortar audio largo</span>
        {pendientes.length > 0 && (
          <span className="rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-black">
            {pendientes.length}
          </span>
        )}
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${
            abierto ? "rotate-180" : ""
          }`}
        />
      </button>

      {abierto && (
        <div className="space-y-3 border-t border-border/60 p-3 pt-2.5">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Sube una charla de YouTube (3-10 min) y se buscan los trozos que
            arrancan con gancho propio y cierran la idea, de 55 a 110 segundos.
            No corta nada hasta que tú elijas.
          </p>

          <div className="grid grid-cols-2 gap-2">
            {ponentes.map((p) => (
              <button
                key={p.slug}
                type="button"
                onClick={() => setPonente(p.slug)}
                className={`truncate rounded-lg border px-3 py-2 text-xs transition ${
                  elegido === p.slug
                    ? "border-amber-500 bg-amber-500/10 font-semibold text-amber-500"
                    : "border-border/60 text-muted-foreground hover:border-foreground/30"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <input
            type="file"
            accept="audio/*,video/mp4"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-xs"
          />
          <button
            type="button"
            disabled={!file || !elegido || subir.isPending}
            onClick={enviar}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-amber-600 disabled:opacity-50"
          >
            {subir.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo…
              </>
            ) : (
              "Analizar (unos minutos)"
            )}
          </button>

          {pendientes.map((prop) => {
            const indices = prop.clips
              .map((_c, i) => i)
              .filter((i) => marcado(prop.fichero, i));
            return (
              <div
                key={`${prop.ponente}/${prop.fichero}`}
                className="space-y-2 rounded-lg border border-border/60 p-2.5"
              >
                <div className="flex items-center gap-2">
                  <p className="min-w-0 flex-1 truncate text-xs font-semibold">
                    {prop.fichero}
                  </p>
                  <span className="shrink-0 text-[10px] text-muted-foreground">
                    {prop.ponente}
                  </span>
                </div>

                {prop.clips.length === 0 && (
                  <p className="text-[11px] text-muted-foreground">
                    Ningún trozo aguanta 50s con gancho propio. Descártalo.
                  </p>
                )}

                {prop.clips.map((c, i) => (
                  <label
                    key={`${c.inicio}-${c.fin}`}
                    className={`flex cursor-pointer gap-2 rounded-lg border p-2 transition ${
                      marcado(prop.fichero, i)
                        ? "border-amber-500/60 bg-amber-500/5"
                        : "border-border/60 opacity-60"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={marcado(prop.fichero, i)}
                      onChange={() => alternar(prop.fichero, i)}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-amber-500"
                    />
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <p className="text-[11px] font-medium">
                        {mmss(c.inicio)} → {mmss(c.fin)}
                        <span className="ml-1.5 text-muted-foreground">
                          ({Math.round(c.duracion)}s) · {c.tema}
                        </span>
                      </p>
                      {/* El gancho es lo que decide si el vídeo retiene: se
                          enseña entero para poder juzgarlo de un vistazo. */}
                      {c.gancho && (
                        <p className="text-[11px] italic leading-snug text-foreground/90">
                          “{c.gancho}”
                        </p>
                      )}
                      {c.porque && (
                        <p className="text-[10px] leading-snug text-muted-foreground">
                          {c.porque}
                        </p>
                      )}
                    </div>
                  </label>
                ))}

                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    disabled={descartar.isPending}
                    onClick={() =>
                      descartar.mutate(
                        { ponente: prop.ponente, fichero: prop.fichero },
                        { onSuccess: () => toast.success("Propuesta descartada") },
                      )
                    }
                    className="rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-destructive disabled:opacity-50"
                  >
                    Descartar
                  </button>
                  <button
                    type="button"
                    disabled={indices.length === 0 || cortar.isPending}
                    onClick={() =>
                      cortar.mutate(
                        { ponente: prop.ponente, fichero: prop.fichero, indices },
                        {
                          onSuccess: (r) => toast.success(r.mensaje),
                          onError: (e) =>
                            toast.error(e instanceof ApiError ? e.message : String(e)),
                        },
                      )
                    }
                    className="rounded-lg bg-amber-500 px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-amber-600 disabled:opacity-50"
                  >
                    {cortar.isPending ? "Cortando…" : `Crear ${indices.length}`}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

/** Valor imposible como nombre de fichero: marca "ninguno elegido todavía".
 *
 *  Hace falta porque la lista VACÍA ya significa "todos" (contrato del
 *  backend, `_audios_de`). Sin este centinela, desmarcar todas las casillas
 *  daba silenciosamente TODOS los audios — justo lo contrario de lo que ve el
 *  operador en pantalla. Al enviar se limpia y se exige elegir al menos uno.
 */
const AUDIO_NINGUNO = "__ninguno__";

/** Qué audios usar de un ponente. Sin marcar ninguno = todos.
 *
 *  Existe porque los audios LARGOS retienen más: los dos vídeos más vistos
 *  del operador salieron del único que pasaba del minuto, así que quiere
 *  poder tirar solo de esos. */
function AudiosDePonente({
  slug,
  label,
  elegidos,
  onChange,
}: {
  slug: string;
  label: string;
  elegidos: string[];
  onChange: (nombres: string[]) => void;
}) {
  const audios = useAudios(slug);
  const items = audios.data ?? [];
  if (audios.isLoading) {
    return <p className="text-[11px] text-muted-foreground">Cargando audios…</p>;
  }
  if (!items.length) return null;

  const ninguno = elegidos.length === 1 && elegidos[0] === AUDIO_NINGUNO;
  const marcado = (n: string) =>
    !ninguno && (elegidos.length === 0 || elegidos.includes(n));
  const largos = items.filter((a) => a.duracion_s >= 60).map((a) => a.nombre);
  const clips = items.filter((a) => a.origen === "clip");
  const nuevos = clips.map((a) => a.nombre);
  // "Los últimos" = los clips de la ÚLTIMA CHARLA analizada, no los de la
  // última hora. Agrupar por tiempo era difuso (dos análisis seguidos caían
  // juntos); el fichero de origen sí es exacto: `clip_<origen>_cN.mp3`.
  const recientes = (() => {
    const origen = (n: string) => n.replace(/^clip_/i, "").replace(/_c\d+\.mp3$/i, "");
    const ultimo = clips.reduce<AudioItem | null>(
      (mejor, a) => ((a.creado_at ?? 0) > (mejor?.creado_at ?? 0) ? a : mejor),
      null,
    );
    if (!ultimo) return [];
    const base = origen(ultimo.nombre);
    return clips.filter((a) => origen(a.nombre) === base).map((a) => a.nombre);
  })();

  return (
    <div className="space-y-1.5 rounded-lg border border-border/60 p-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold">Audios de {label}</p>
        <div className="flex gap-1">
          {largos.length > 0 && (
            <button
              type="button"
              onClick={() => onChange(largos)}
              className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] transition hover:border-foreground/40"
            >
              Solo +1 min ({largos.length})
            </button>
          )}
          {/* Para probar de golpe los arranques nuevos sacados de YouTube. */}
          {nuevos.length > 0 && (
            <button
              type="button"
              onClick={() => onChange(nuevos)}
              className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] transition hover:border-amber-500 hover:text-amber-500"
            >
              Solo clips ({nuevos.length})
            </button>
          )}
          {recientes.length > 0 && recientes.length < nuevos.length && (
            <button
              type="button"
              onClick={() => onChange(recientes)}
              className="rounded border border-amber-500/60 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-500 transition hover:bg-amber-500/20"
            >
              Solo la última charla ({recientes.length})
            </button>
          )}
          <button
            type="button"
            onClick={() => onChange([])}
            className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] transition hover:border-foreground/40"
          >
            Todos ({items.length})
          </button>
          <button
            type="button"
            onClick={() => onChange([AUDIO_NINGUNO])}
            className="rounded border border-border/60 px-1.5 py-0.5 text-[10px] transition hover:border-foreground/40"
          >
            Ninguno
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
        {items.map((a) => (
          <label
            key={a.nombre}
            className="flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 text-[11px] hover:bg-muted/40"
          >
            <input
              type="checkbox"
              checked={marcado(a.nombre)}
              onChange={(e) => {
                // La lista vacía significa "todos": al desmarcar el primero
                // hay que materializarla, si no se entendería al revés.
                const base = ninguno
                  ? []
                  : elegidos.length
                    ? elegidos
                    : items.map((x) => x.nombre);
                const next = e.target.checked
                  ? [...base, a.nombre]
                  : base.filter((n) => n !== a.nombre);
                // Vacío = "todos" para el backend, así que al quedarse sin
                // ninguna marcada se pone el centinela, no `[]`.
                onChange(
                  next.length === items.length
                    ? []
                    : next.length === 0
                      ? [AUDIO_NINGUNO]
                      : next,
                );
              }}
              className="h-3 w-3 shrink-0"
            />
            {/* Los clips sacados de una charla larga se marcan: se eligen
                igual que los demás, pero el operador quiere saber cuáles ha
                propuesto la máquina y cuáles recortó él. */}
            {a.origen === "clip" && (
              <Scissors
                className="h-3 w-3 shrink-0 text-amber-500"
                aria-label="clip automático"
              />
            )}
            <span className="min-w-0 flex-1 truncate">
              {a.nombre.replace(/^clip_/i, "").replace(/\.mp3$/i, "")}
            </span>
            {/* La fecha ordena mentalmente el banco: cuáles son los de siempre
                y cuáles acaban de entrar. Solo en los clips — los audios base
                llevan ahí desde el principio. */}
            {a.origen === "clip" && a.creado_at ? (
              <span className="shrink-0 text-[10px] text-muted-foreground">
                {new Date(a.creado_at * 1000).toLocaleDateString("es-ES", {
                  day: "numeric",
                  month: "short",
                })}
              </span>
            ) : null}
            <span
              className={`shrink-0 tabular-nums ${
                a.duracion_s >= 60 ? "font-semibold text-emerald-500" : "text-muted-foreground"
              }`}
            >
              {mmss(a.duracion_s)}
            </span>
          </label>
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground">
        {elegidos.length === 0
          ? `Se usarán los ${items.length}.`
          : `Se usarán ${elegidos.length} de ${items.length}.`}
      </p>
    </div>
  );
}

export default function ViralizacionPage() {
  const openQueue = useDrawerStore((s) => s.openQueue);
  const ponentesQuery = usePonentes();
  const generate = useGenerateViralizacion();

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  // Audios elegidos por ponente. Lista vacía = todos los del banco.
  const [audiosPorPonente, setAudiosPorPonente] = useState<Record<string, string[]>>({});
  const [cantidad, setCantidad] = useState<Record<string, number>>({});
  const [nombreCuenta, setNombreCuenta] = useState("");
  // Sin música de fondo salvo que se marque a propósito.
  // "no" | "mitad" | "todos", igual que el CTA. Antes era un contador de
  // RONDAS y "1 ronda" parecía "todos": lo era mientras no pidieras más
  // vídeos que audios, y a partir de ahí se quedaban sin música la mitad.
  const [musica, setMusica] = useState<"no" | "mitad" | "todos">("no");
  // CTA final hablado. Solo tiene sentido con Pablo: Víctor ya lo trae dentro
  // de sus audios, así que el selector no se enseña si no está él.
  const [ctaFinal, setCtaFinal] = useState<"no" | "todos" | "mitad">("no");
  const [success, setSuccess] = useState<{ total: number; position: number } | null>(null);

  const ponentes = ponentesQuery.data?.items ?? [];
  const selectedSlugs = Object.keys(selected).filter((slug) => selected[slug]);
  // Coletillas de CTA grabadas para Pablo (0 = no se puede ofrecer).
  const ctasPablo = ponentes.find((p) => p.slug === "pablo")?.n_ctas ?? 0;

  // Estilo por ronda. El plan se calcula sobre el primer ponente elegido: el
  // reparto en rondas depende de cuántos audios tiene, y las rondas son el
  // "ciclo" que el operador quiere diferenciar.
  // "__nueva__" = escribir un nombre a mano; si no, se reutiliza una carpeta
  // que ya existe en Drive.
  const [carpetaExistente, setCarpetaExistente] = useState("__nueva__");
  const carpetas = useCarpetas();
  const today = new Date().toISOString().slice(0, 10);

  const [roundStyles, setRoundStyles] = useState<string[]>([]);
  // Estilos marcados. Por defecto TODOS: el reparto equitativo entre los 6 es
  // lo que da variedad a una tanda grande.
  const [stylesPool, setStylesPool] = useState<string[]>([]);
  const estilos = useEstilos();
  const planPonente = selectedSlugs[0] ?? null;
  const planCantidad = planPonente ? (cantidad[planPonente] ?? 5) : 0;
  const plan = useRoundPlan(planPonente, planCantidad);

  // Al cambiar el reparto, arrancar desde los estilos por defecto (la
  // rotación) para que lo que se envía siempre case con las rondas reales.
  useEffect(() => {
    const rounds = plan.data?.rounds;
    if (rounds) setRoundStyles(rounds.map((r) => r.default_style));
  }, [plan.data]);

  const canSubmit =
    selectedSlugs.length > 0 && nombreCuenta.trim().length > 0 && !generate.isPending;

  function toggle(slug: string, checked: boolean) {
    setSelected((prev) => ({ ...prev, [slug]: checked }));
    setCantidad((prev) => (prev[slug] != null ? prev : { ...prev, [slug]: 5 }));
  }

  async function submit() {
    if (!canSubmit) return;
    // Sin ningún audio marcado no se puede generar: el backend entiende la
    // lista vacía como "todos" y saldría una tanda que nadie ha pedido.
    const sinAudios = selectedSlugs.filter((slug) => {
      const lista = audiosPorPonente[slug] ?? [];
      return lista.length === 1 && lista[0] === AUDIO_NINGUNO;
    });
    if (sinAudios.length) {
      toast.error(
        `Marca al menos un audio de ${sinAudios.join(", ")} (o pulsa «Todos»).`,
      );
      return;
    }
    setSuccess(null);
    const body = {
      ponentes: selectedSlugs,
      cantidad: Object.fromEntries(
        selectedSlugs.map((slug) => [slug, cantidad[slug] ?? 5]),
      ),
      nombre_cuenta: nombreCuenta.trim(),
      music_rounds: musica === "no" ? 0 : 1,
      round_styles: roundStyles,
      styles_pool: stylesPool,
      musica,
      cta_final: ctaFinal,
      audios: Object.fromEntries(
        selectedSlugs
          .map((slug) => [slug, audiosPorPonente[slug] ?? []])
          .filter(([, lista]) => (lista as string[]).length > 0),
      ),
    };
    try {
      const res = await generate.mutateAsync(body);
      toast.success(`Job encolado — ${res.total_videos} vídeos · posición ${res.position_in_queue} en la cola`);
      setSuccess({ total: res.total_videos, position: res.position_in_queue });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Error inesperado");
    }
  }

  return (
    <div className="container mx-auto space-y-4 p-3 sm:space-y-6 sm:p-6 md:p-10">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
          <Rocket className="h-5 w-5 text-amber-500 sm:h-6 sm:w-6" />
          Viralización 1K
        </h1>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Genera en lote vídeos POV/reacción (voz de ponente + B-roll paisaje) para
          hacer crecer una cuenta hasta 1000 seguidores.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold sm:text-base">Ponentes</h2>
        {ponentesQuery.isLoading && (
          <p className="text-xs text-muted-foreground">Cargando ponentes…</p>
        )}
        {ponentesQuery.isError && (
          <p className="text-xs text-destructive">No se pudieron cargar los ponentes.</p>
        )}
        {!ponentesQuery.isLoading && ponentes.length === 0 && !ponentesQuery.isError && (
          <p className="text-xs text-muted-foreground">No hay ponentes disponibles.</p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {ponentes.map((p) => {
            const disabled = p.n_audios <= 0;
            const isSelected = !disabled && !!selected[p.slug];
            return (
              <div
                key={p.slug}
                className="space-y-2 rounded-lg border border-border p-3 text-xs sm:text-sm"
              >
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 shrink-0 accent-amber-500"
                    checked={isSelected}
                    disabled={disabled}
                    onChange={(e) => toggle(p.slug, e.target.checked)}
                  />
                  <span>
                    <span className="font-medium">{p.label}</span>
                    {" — "}
                    {p.n_audios} audio{p.n_audios === 1 ? "" : "s"} disponible
                    {p.n_audios === 1 ? "" : "s"}
                    <span className="block text-[10px] text-muted-foreground">
                      gancho: {p.hooks_available}/{p.hooks_total} libres · paisaje:{" "}
                      {p.paisajes_available}/{p.paisajes_total} libres
                    </span>
                    {disabled && (
                      <span className="block text-[10px] text-destructive">
                        Sin audios disponibles — no se puede seleccionar.
                      </span>
                    )}
                  </span>
                </label>
                {isSelected && (
                  <div className="flex items-center gap-2 pl-6">
                    <span className="text-[11px] text-muted-foreground">¿Cuántos vídeos?</span>
                    <input
                      type="number"
                      min={1}
                      value={cantidad[p.slug] ?? 5}
                      onChange={(e) =>
                        setCantidad((prev) => ({
                          ...prev,
                          [p.slug]: Math.max(1, Number(e.target.value) || 1),
                        }))
                      }
                      className="w-16 rounded-md border border-border bg-background px-2 py-0.5 text-xs"
                    />
                  </div>
                )}
                {isSelected && (
                  <div className="pl-6">
                    <AudiosDePonente
                      slug={p.slug}
                      label={p.label ?? p.slug}
                      elegidos={audiosPorPonente[p.slug] ?? []}
                      onChange={(nombres) =>
                        setAudiosPorPonente((prev) => ({ ...prev, [p.slug]: nombres }))
                      }
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="col-span-2 sm:col-span-1">
          <span className="mb-1 block text-xs font-medium sm:text-sm">
            Carpeta de destino *
          </span>
          {/* Desplegable con las carpetas que ya existen en Drive, para no
              tener que recordar el nombre exacto y poder acumular tandas. */}
          <select
            value={carpetaExistente}
            onChange={(e) => {
              const v = e.target.value;
              setCarpetaExistente(v);
              if (v !== "__nueva__") setNombreCuenta(v);
              else setNombreCuenta("");
            }}
            className="mb-1.5 w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:text-sm"
          >
            <option value="__nueva__">➕ Carpeta nueva…</option>
            {(carpetas.data?.items ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {carpetaExistente === "__nueva__" && (
            <input
              type="text"
              value={nombreCuenta}
              onChange={(e) => setNombreCuenta(e.target.value)}
              placeholder="nombre de la carpeta nueva"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:text-sm"
            />
          )}
          <p className="mt-1 text-[10px] text-muted-foreground">
            Se guardará en <code>VIRALIZACION/{nombreCuenta || "…"}/</code>, con
            una subcarpeta por ponente (p. ej. <code>32_pablo_{today}</code>).
          </p>
        </div>
        {/* Música de fondo: APAGADA por defecto. Antes se colaba siempre en
            la ronda 1 aunque no se pidiera. */}
        {/* CTA final hablado. Solo con Pablo: Víctor ya lo trae dentro de sus
            audios, así que enseñarlo con él sería ofrecer duplicarlo. */}
        {selectedSlugs.includes("pablo") && (
          <div>
            <span className="mb-1 block text-xs font-medium sm:text-sm">
              CTA final hablado
            </span>
            {/* Sin audios grabados la opción no puede hacer NADA: elegirla
                daba vídeos sin coletilla y sin avisar de por qué. */}
            {ctasPablo === 0 ? (
              <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-relaxed text-amber-500">
                No hay ninguna coletilla grabada todavía, así que esta opción no
                haría nada. Graba la frase («no te olvides de seguirme…») y
                deja el audio en <code>viralizacion_assets/pablo/cta/</code>;
                en cuanto haya uno, aquí salen las opciones.
              </p>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-1.5">
                  {([
                    ["no", "Sin CTA"],
                    ["mitad", "A la mitad"],
                    ["todos", "A todos"],
                  ] as const).map(([valor, etiqueta]) => (
                    <button
                      key={valor}
                      type="button"
                      onClick={() => setCtaFinal(valor)}
                      className={`truncate rounded-md border px-2 py-1.5 text-xs transition ${
                        ctaFinal === valor
                          ? "border-amber-500 bg-amber-500/15 font-semibold text-amber-500"
                          : "border-border text-muted-foreground hover:border-foreground/40"
                      }`}
                    >
                      {etiqueta}
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
                  {ctasPablo} coletilla{ctasPablo > 1 ? "s" : ""} grabada
                  {ctasPablo > 1 ? "s" : ""}, sin subtítulos. «A la mitad» la
                  reparte alternando dentro de cada audio, para que compares el
                  CTA y no el audio. Solo Pablo — Víctor ya la lleva en los
                  suyos.
                </p>
              </>
            )}
          </div>
        )}

        <div>
          <span className="mb-1 block text-xs font-medium sm:text-sm">
            Música de fondo
          </span>
          {/* Mismo vocabulario que el CTA. Antes era un contador de RONDAS y
              "1 ronda" parecía "todos": lo era mientras no pidieras más vídeos
              que audios, y a partir de ahí la mitad salían sin música sin que
              nada lo dijera. */}
          <div className="grid grid-cols-3 gap-1.5">
            {([
              ["no", "Sin música"],
              ["mitad", "A la mitad"],
              ["todos", "A todos"],
            ] as const).map(([valor, etiqueta]) => (
              <button
                key={valor}
                type="button"
                onClick={() => setMusica(valor)}
                className={`truncate rounded-md border px-2 py-1.5 text-xs transition ${
                  musica === valor
                    ? "border-amber-500 bg-amber-500/15 font-semibold text-amber-500"
                    : "border-border text-muted-foreground hover:border-foreground/40"
                }`}
              >
                {etiqueta}
              </button>
            ))}
          </div>
          <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
            «A todos» la pone en todos los vídeos, pidas los que pidas. «A la
            mitad» alterna vídeo sí, vídeo no, para comparar con y sin.
          </p>
        </div>
      </section>

      {/* Versiones a generar: se reparten a partes iguales entre las marcadas.
          Antes el estilo iba por RONDA y las rondas dependían del nº de audios,
          así que con 25 vídeos y 8 audios solo salían 4 de los 6 estilos. */}
      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Palette className="h-4 w-4 shrink-0 text-amber-500" />
          <p className="text-sm font-semibold">Versiones a generar</p>
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Marca las versiones que quieres. Los vídeos se reparten entre ellas a
          partes iguales. Sin marcar ninguna se usan todas. Cada muestra son dos
          fotogramas del mismo vídeo: gancho y paisaje.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {(estilos.data?.items ?? []).map((s) => {
            const marcado = stylesPool.length === 0 || stylesPool.includes(s.key);
            return (
              <label
                key={s.key}
                className={`flex cursor-pointer flex-col gap-1.5 rounded-md border p-1.5 text-xs transition sm:text-sm ${
                  marcado
                    ? "border-amber-500/60 bg-amber-500/10"
                    : "border-border/60 text-muted-foreground opacity-60"
                }`}
              >
                {/* Miniatura de muestra: sin ella el operador elige a ciegas —
                    "B · Reveal" no dice nada sobre qué hace el estilo.
                    Generadas con scripts/viralizacion_previews.py. */}
                <img
                  src={`/viralizacion/previews/${s.key}.jpg`}
                  alt={s.label}
                  loading="lazy"
                  className="aspect-[9/8] w-full rounded bg-black object-cover"
                />
                <span className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    className="h-4 w-4 shrink-0 accent-amber-500"
                    checked={marcado}
                    onChange={(e) => {
                      const todos = (estilos.data?.items ?? []).map((x) => x.key);
                      // Lista vacía = "todas". Al desmarcar la primera hay que
                      // materializar la lista completa para poder quitar una.
                      const base = stylesPool.length === 0 ? todos : stylesPool;
                      setStylesPool(
                        e.target.checked
                          ? Array.from(new Set([...base, s.key]))
                          : base.filter((k) => k !== s.key),
                      );
                    }}
                  />
                  <span className="truncate">{s.label}</span>
                </span>
              </label>
            );
          })}
        </div>
        {(() => {
          const n = selectedSlugs.reduce((acc, slug) => acc + (cantidad[slug] ?? 5), 0);
          const nEst = stylesPool.length || (estilos.data?.items?.length ?? 8);
          if (!n || !nEst) return null;
          const base = Math.floor(n / nEst);
          const resto = n % nEst;
          return (
            <p className="text-[10px] text-muted-foreground">
              {n} vídeo(s) entre {nEst} versión(es) →{" "}
              {resto === 0
                ? `${base} de cada una`
                : `${resto} versión(es) con ${base + 1} y el resto con ${base}`}
              .
            </p>
          );
        })()}
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={submit}
          className="inline-flex items-center gap-1.5 rounded-md bg-amber-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {generate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
          {generate.isPending ? "Encolando…" : "Generar"}
        </button>
        {success && (
          <button
            type="button"
            onClick={openQueue}
            className="text-xs font-medium text-amber-600 hover:underline sm:text-sm"
          >
            Ver cola →
          </button>
        )}
      </div>

      {/* Material de consulta, no parte del flujo: se mira de vez en cuando,
          así que va DESPUÉS del botón de generar y no antes de los ponentes. */}
      <CortarAudioLargo ponentes={ponentes} />
      <CuentasEjemplo />
    </div>
  );
}
