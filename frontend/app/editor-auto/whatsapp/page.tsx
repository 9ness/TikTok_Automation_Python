"use client";

import { Check, Copy, HelpCircle, Loader2, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  useWaConversacion,
  useWaConversaciones,
  useWaDiagnostico,
  useWaPausa,
  useWaPlantillas,
  useWaPrueba,
  useWaReanudar,
  useWaSuscribir,
} from "@/lib/queries/editor-whatsapp";
import type { WaConversacion, WaSobre } from "@/lib/types/editor-whatsapp";
import { cn } from "@/lib/utils";

const HORA = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
const FECHA = (ts: number) =>
  new Date(ts * 1000).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

function msgSobre<T>(r: WaSobre<T> | undefined): string | null {
  if (!r) return null;
  if (!r.configurado) return "El bot no está desplegado todavía.";
  if (!r.alcanzable) return r.error || "No se llega al bot.";
  return null;
}

const CHIP_OK = "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
const CHIP_WARN = "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400";
const CHIP_BAD = "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400";
const CHIP_OFF = "border-border bg-muted text-muted-foreground";

function chipEstado(estado: string): string {
  const e = (estado || "").toUpperCase();
  if (e === "APPROVED") return CHIP_OK;
  if (e === "PENDING") return CHIP_WARN;
  if (e === "REJECTED") return CHIP_BAD;
  return CHIP_OFF;
}

function Pasos({ n, items }: { n: number; items: string[] }) {
  return (
    <ol className="space-y-2">
      {items.slice(0, n).map((t, i) => (
        <li key={i} className="flex gap-2 text-xs sm:text-sm">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-violet/15 text-[11px] font-semibold text-brand-violet">
            {i + 1}
          </span>
          <span className="min-w-0 break-words">{t}</span>
        </li>
      ))}
    </ol>
  );
}

const PASOS_360 = [
  "Crea la cuenta en hub.360dialog.com con el Facebook del negocio.",
  "«Add channel» → «WhatsApp Business App» y escanea el QR desde la app de WhatsApp Business (hay que tenerla actualizada).",
  "Copia la API key del canal y métela en el servidor con `clave whatsapp-bot D360_API_KEY`.",
  "Pulsa «Comprobar otra vez»: el webhook se configura solo con el botón «Suscribir webhook».",
];
const PASOS_META = [
  "En developers.facebook.com crea una app de tipo Business y añade el producto WhatsApp.",
  "Añade un número que NO esté en la app de WhatsApp y verifícalo por SMS.",
  "En Configuración del negocio crea un usuario del sistema con token permanente (permisos whatsapp_business_messaging y whatsapp_business_management).",
  "Mete con `clave whatsapp-bot` estas variables: WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_WABA_ID.",
  "En la app de Meta → WhatsApp → Configuración → Webhook pega la URL de abajo y el token de verificación (`WHATSAPP_VERIFY_TOKEN`, lo genera el despliegue) y suscribe el campo `messages`.",
  "Pulsa «Comprobar otra vez».",
];

export default function EditorAutoWhatsappPage() {
  const diag = useWaDiagnostico();
  const sobre = diag.data;
  const datos = sobre && sobre.configurado && sobre.alcanzable ? sobre.datos : undefined;
  const conectado = !!datos;

  const conv = useWaConversaciones(50, conectado);
  const plantillas = useWaPlantillas();
  const suscribir = useWaSuscribir();
  const prueba = useWaPrueba();
  const pausa = useWaPausa();
  const reanudar = useWaReanudar();

  const [telefono, setTelefono] = useState("");
  const [abierta, setAbierta] = useState<WaConversacion | null>(null);
  const [resPlantillas, setResPlantillas] = useState<{
    enviadas: string[];
    ya_estaban: string[];
    errores: { nombre: string; error: string }[];
  } | null>(null);

  // Estado general
  let estado: { texto: string; clase: string; extra?: string };
  if (diag.isLoading) {
    estado = { texto: "Comprobando…", clase: CHIP_OFF };
  } else if (diag.isError || !sobre) {
    estado = { texto: "No se llega al bot", clase: CHIP_BAD, extra: "La API no respondió." };
  } else if (!sobre.configurado) {
    estado = {
      texto: "El bot no está desplegado todavía",
      clase: CHIP_OFF,
      extra: sobre.faltan?.length
        ? `Faltan en la API: ${sobre.faltan.join(", ")}`
        : undefined,
    };
  } else if (!sobre.alcanzable) {
    estado = { texto: "No se llega al bot", clase: CHIP_BAD, extra: sobre.error };
  } else if (datos?.listo) {
    estado = { texto: "Conectado", clase: CHIP_OK };
  } else {
    estado = { texto: "Faltan pasos", clase: CHIP_WARN };
  }

  const proveedor = datos?.proveedor;
  const webhookUrl = datos?.webhook?.url ?? "";
  const mes = datos?.mes;
  const propuestas = datos?.plantillas_propuestas ?? [];
  const pasos = datos?.pasos ?? [];
  const faltan = datos?.faltan ?? [];
  const ahora = Date.now() / 1000;

  function copiar(t: string) {
    navigator.clipboard?.writeText(t).then(
      () => toast.success("Copiado"),
      () => toast.error("No se pudo copiar"),
    );
  }

  async function enviarPlantillas() {
    try {
      const r = await plantillas.mutateAsync();
      const m = msgSobre(r);
      if (m) return toast.error(m);
      if (r.configurado && r.alcanzable) {
        setResPlantillas({
          enviadas: r.datos?.enviadas ?? [],
          ya_estaban: r.datos?.ya_estaban ?? [],
          errores: r.datos?.errores ?? [],
        });
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  async function accionOk(fn: () => Promise<WaSobre<{ ok: boolean; error?: string }>>, ok: string) {
    try {
      const r = await fn();
      const m = msgSobre(r);
      if (m) return toast.error(m);
      if (r.configurado && r.alcanzable) {
        if (r.datos?.ok) toast.success(ok);
        else toast.error(r.datos?.error || "No se pudo");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    }
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">Conectar WhatsApp</h1>
          <p className="text-xs text-muted-foreground sm:text-sm">
            Bot que contesta los mensajes de WhatsApp del negocio. Aquí se conecta, se comprueba
            y se vigilan las conversaciones.
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Badge className={cn("border", estado.clase)}>{estado.texto}</Badge>
            {estado.extra && (
              <span className="min-w-0 break-words text-xs text-muted-foreground">
                {estado.extra}
              </span>
            )}
          </div>
        </div>
        <Button
          variant="outline"
          onClick={() => diag.refetch()}
          disabled={diag.isFetching}
          className="w-full sm:w-auto"
        >
          {diag.isFetching ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Comprobar otra vez
        </Button>
      </header>

      {/* b) Elegir cómo conectar */}
      <section className="space-y-3">
        <h2 className="text-base font-semibold sm:text-lg">Elige cómo conectar</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Card className={cn(proveedor === "360dialog" && "border-emerald-500/60 ring-1 ring-emerald-500/40")}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2 text-sm sm:text-base">
                <span className="min-w-0 break-words">
                  Seguir usando la app del móvil (coexistencia) · con 360dialog · 49 €/mes
                </span>
                {proveedor === "360dialog" && <Badge className={cn("border", CHIP_OK)}>En uso</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Pasos n={PASOS_360.length} items={PASOS_360} />
            </CardContent>
          </Card>
          <Card className={cn(proveedor === "meta" && "border-emerald-500/60 ring-1 ring-emerald-500/40")}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2 text-sm sm:text-base">
                <span className="min-w-0 break-words">Número aparte, gratis (Cloud API de Meta)</span>
                {proveedor === "meta" && <Badge className={cn("border", CHIP_OK)}>En uso</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Pasos n={PASOS_META.length} items={PASOS_META} />
            </CardContent>
          </Card>
        </div>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Seguir contestando desde la app del móvil solo es posible a través de un proveedor oficial
          (Meta lo reserva a sus partners). Desde el 1 de octubre de 2026 Meta regala 1.000 mensajes
          de servicio al mes por número; el bot se frena solo antes de llegar.
        </p>
      </section>

      {conectado && datos && (
        <>
          {/* c) Comprobaciones */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base sm:text-lg">Comprobaciones</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-2">
                {pasos.map((p) => (
                  <li key={p.id} className="flex items-start gap-2 text-xs sm:text-sm">
                    {p.ok === true ? (
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                    ) : p.ok === false ? (
                      <X className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                    ) : (
                      <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                    <div className="min-w-0">
                      <div className="break-words font-medium">{p.titulo}</div>
                      {p.detalle && (
                        <div className="break-words text-muted-foreground">{p.detalle}</div>
                      )}
                    </div>
                  </li>
                ))}
                {pasos.length === 0 && (
                  <li className="text-xs text-muted-foreground sm:text-sm">Sin comprobaciones.</li>
                )}
              </ul>

              <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2 sm:text-sm">
                <div className="min-w-0 space-y-1">
                  <div className="font-medium">URL del webhook</div>
                  <div className="flex items-start gap-2">
                    <code className="min-w-0 flex-1 break-all rounded bg-muted px-2 py-1 text-[11px] sm:text-xs">
                      {webhookUrl || "—"}
                    </code>
                    {webhookUrl && (
                      <Button size="sm" variant="outline" onClick={() => copiar(webhookUrl)}>
                        <Copy className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                  <div className="text-muted-foreground">
                    Verificado:{" "}
                    {datos.webhook?.verificado ? FECHA(datos.webhook.verificado) : "nunca"} · Último
                    recibido:{" "}
                    {datos.webhook?.ultimo_recibido ? FECHA(datos.webhook.ultimo_recibido) : "nunca"}
                  </div>
                </div>
                <div className="min-w-0 space-y-1">
                  <div className="font-medium">Número</div>
                  {datos.numero ? (
                    <div className="break-words text-muted-foreground">
                      {datos.numero.telefono} · {datos.numero.nombre || "sin nombre"} · calidad{" "}
                      {datos.numero.calidad || "?"}
                    </div>
                  ) : (
                    <div className="text-muted-foreground">Sin número todavía.</div>
                  )}
                  <div className="font-medium pt-1">Mensajes este mes</div>
                  <div className="text-muted-foreground">
                    {mes?.enviados ?? 0} / {mes?.tope ?? 0}
                  </div>
                  <div className="font-medium pt-1">Horario</div>
                  <div className="flex flex-wrap items-center gap-2 text-muted-foreground">
                    <span className="break-words">{datos.horario || "—"}</span>
                    <Badge className={cn("border", datos.abierto_ahora ? CHIP_OK : CHIP_OFF)}>
                      {datos.abierto_ahora ? "Abierto ahora" : "Cerrado ahora"}
                    </Badge>
                  </div>
                </div>
              </div>

              {faltan.length > 0 && (
                <div className="space-y-1 text-xs sm:text-sm">
                  <div className="font-medium">Variables que faltan en el bot</div>
                  <div className="flex flex-wrap gap-1">
                    {faltan.map((f) => (
                      <code key={f} className="break-all rounded bg-amber-500/10 px-2 py-0.5 text-[11px]">
                        {f}
                      </code>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* d) Plantillas */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base sm:text-lg">Plantillas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {propuestas.map((p) => (
                  <div key={p.nombre} className="min-w-0 space-y-1 rounded-md border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="break-all text-xs font-medium sm:text-sm">{p.nombre}</span>
                      <Badge className={cn("border", chipEstado(p.estado))}>
                        {p.estado || "sin_enviar"}
                      </Badge>
                      <span className="text-[11px] text-muted-foreground">{p.categoria}</span>
                    </div>
                    <p className="whitespace-pre-wrap break-words text-xs text-muted-foreground sm:text-sm">
                      {p.texto}
                    </p>
                  </div>
                ))}
                {propuestas.length === 0 && (
                  <p className="text-xs text-muted-foreground sm:text-sm">Sin plantillas propuestas.</p>
                )}
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button onClick={enviarPlantillas} disabled={plantillas.isPending} className="w-full sm:w-auto">
                  {plantillas.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Enviar a aprobar
                </Button>
                <Button
                  variant="outline"
                  disabled={suscribir.isPending}
                  onClick={() => accionOk(() => suscribir.mutateAsync(), "Webhook suscrito")}
                  className="w-full sm:w-auto"
                >
                  {suscribir.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Suscribir webhook
                </Button>
              </div>
              {resPlantillas && (
                <div className="space-y-1 text-xs sm:text-sm">
                  <div className="break-words">Enviadas: {resPlantillas.enviadas.join(", ") || "ninguna"}</div>
                  <div className="break-words">Ya estaban: {resPlantillas.ya_estaban.join(", ") || "ninguna"}</div>
                  {resPlantillas.errores.map((e) => (
                    <div key={e.nombre} className="break-words text-red-500">
                      {e.nombre}: {e.error}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* e) Mensaje de prueba */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base sm:text-lg">Mensaje de prueba</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  value={telefono}
                  onChange={(e) => setTelefono(e.target.value)}
                  placeholder="Teléfono con prefijo, p. ej. 34600111222"
                  inputMode="tel"
                  className="sm:max-w-xs"
                />
                <Button
                  disabled={!telefono.trim() || prueba.isPending}
                  onClick={() =>
                    accionOk(
                      () => prueba.mutateAsync({ telefono: telefono.trim() }),
                      "Mensaje de prueba enviado",
                    )
                  }
                  className="w-full sm:w-auto"
                >
                  {prueba.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Enviar
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Solo llega si ese número ha escrito al bot en las últimas 24 h.
              </p>
            </CardContent>
          </Card>

          {/* f) Conversaciones */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base sm:text-lg">Conversaciones</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {msgSobre(conv.data) && (
                <p className="text-xs text-muted-foreground sm:text-sm">{msgSobre(conv.data)}</p>
              )}
              {(() => {
                const lista =
                  conv.data && conv.data.configurado && conv.data.alcanzable
                    ? (conv.data.datos?.conversaciones ?? [])
                    : [];
                if (conv.isLoading) return <Loader2 className="h-4 w-4 animate-spin" />;
                if (lista.length === 0)
                  return <p className="text-xs text-muted-foreground sm:text-sm">Sin conversaciones.</p>;
                return lista.map((c) => {
                  const pausado = (c.pausado_hasta ?? 0) > ahora;
                  return (
                    <div
                      key={c.wa_id}
                      className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center"
                    >
                      <button
                        type="button"
                        onClick={() => setAbierta(c)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="break-words text-xs font-medium sm:text-sm">
                            {c.nombre || c.wa_id}
                          </span>
                          <span className="text-[11px] text-muted-foreground">{c.mensajes} msj</span>
                          {pausado && (
                            <Badge className={cn("border", CHIP_WARN)}>
                              Bot en pausa hasta {HORA(c.pausado_hasta)}
                            </Badge>
                          )}
                        </div>
                        <div className="truncate text-xs text-muted-foreground">{c.ultimo_texto}</div>
                      </button>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={pausa.isPending}
                          onClick={() =>
                            accionOk(
                              () => pausa.mutateAsync({ wa_id: c.wa_id, minutos: 120 }),
                              "Bot en pausa 2 h",
                            )
                          }
                        >
                          Pausar 2 h
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={reanudar.isPending}
                          onClick={() =>
                            accionOk(() => reanudar.mutateAsync({ wa_id: c.wa_id }), "Bot reanudado")
                          }
                        >
                          Reanudar
                        </Button>
                      </div>
                    </div>
                  );
                });
              })()}
            </CardContent>
          </Card>
        </>
      )}

      <Hilo conv={abierta} onClose={() => setAbierta(null)} />
    </div>
  );
}

function Hilo({ conv, onClose }: { conv: WaConversacion | null; onClose: () => void }) {
  const q = useWaConversacion(conv?.wa_id ?? null);
  const mensajes =
    q.data && q.data.configurado && q.data.alcanzable ? (q.data.datos?.mensajes ?? []) : [];
  return (
    <Dialog open={!!conv} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="break-words text-base">{conv?.nombre || conv?.wa_id}</DialogTitle>
          <DialogDescription className="break-all text-xs">{conv?.wa_id}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {q.isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
          {msgSobre(q.data) && (
            <p className="text-xs text-muted-foreground">{msgSobre(q.data)}</p>
          )}
          {mensajes.map((m, i) => (
            <div
              key={i}
              className={cn("flex", m.direccion === "entra" ? "justify-start" : "justify-end")}
            >
              <div
                className={cn(
                  "max-w-[85%] rounded-lg px-3 py-2 text-xs sm:text-sm",
                  m.direccion === "entra" && "bg-muted",
                  m.direccion === "sale" && "bg-brand-violet/15",
                  m.direccion === "eco" && "border border-amber-500/40 bg-amber-500/10",
                )}
              >
                <div className="whitespace-pre-wrap break-words">{m.texto}</div>
                <div className="mt-1 text-[10px] text-muted-foreground">
                  {m.direccion === "entra" ? "Cliente" : m.direccion === "sale" ? "Bot" : "Néstor (móvil)"}{" "}
                  · {FECHA(m.ts)}
                </div>
              </div>
            </div>
          ))}
          {!q.isLoading && mensajes.length === 0 && !msgSobre(q.data) && (
            <p className="text-xs text-muted-foreground">Sin mensajes.</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
