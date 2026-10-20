"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";

/** Conectar Meta pegando el token aquí, no en un chat.
 *
 *  Facebook: un token de USUARIO de larga duración → el servidor saca el de
 *  cada página (no caduca) y lo usa también para Instagram. Threads: un token
 *  por cuenta, se casa solo por el id. Nunca se enseña ningún token de vuelta.
 */
function Bloque({ titulo, ayuda, ruta }: { titulo: string; ayuda: string; ruta: string }) {
  const [token, setToken] = useState("");
  const [estado, setEstado] = useState<{ ok: boolean; texto: string } | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar() {
    setEnviando(true);
    setEstado(null);
    try {
      const r = await api.post<Record<string, unknown>>(ruta, { token: token.trim() });
      setToken("");
      if (Array.isArray(r.conectadas)) {
        const nombres = (r.conectadas as { cuenta: string; pagina: string }[])
          .map((c) => `${c.cuenta} (${c.pagina})`)
          .join(", ");
        setEstado({ ok: r.conectadas.length > 0, texto: `Conectadas: ${nombres || "ninguna"}` });
      } else {
        setEstado({ ok: true, texto: `Conectada: ${r.cuenta} (@${r.usuario})` });
      }
    } catch (e) {
      setEstado({ ok: false, texto: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base sm:text-lg">{titulo}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground sm:text-sm">{ayuda}</p>
        <Textarea
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Pega aquí el token"
          rows={3}
          autoComplete="off"
          spellCheck={false}
          className="break-all font-mono text-xs"
        />
        <Button onClick={enviar} disabled={!token.trim() || enviando} className="w-full sm:w-auto">
          {enviando ? "Conectando…" : "Conectar"}
        </Button>
        {estado && (
          <p className={`break-words text-xs sm:text-sm ${estado.ok ? "text-emerald-600" : "text-red-600"}`}>
            {estado.texto}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Threads por OAuth: el «Generador de identificadores» de Meta falla desde el
 *  navegador de Messenger, así que el permiso se pide desde aquí y vuelve a
 *  `/meta/threads/retorno`, que guarda el token (y el tick lo renueva). */
function ThreadsOAuth() {
  const [app, setApp] = useState<{ configurada: boolean; app_id: string; url_retorno: string } | null>(null);
  const [appId, setAppId] = useState("");
  const [secreto, setSecreto] = useState("");
  const [estado, setEstado] = useState<{ ok: boolean; texto: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function cargar() {
    try {
      const r = await api.get<{ configurada: boolean; app_id: string; url_retorno: string }>(
        "/api/v1/multiplataforma/meta/threads/app",
      );
      setApp(r);
      setAppId((v) => v || r.app_id);
    } catch (e) {
      setEstado({ ok: false, texto: e instanceof ApiError ? e.message : String(e) });
    }
  }

  useEffect(() => {
    cargar();
    const q = new URLSearchParams(window.location.search);
    if (q.get("threads") === "ok") {
      setEstado({ ok: true, texto: `Conectada: ${q.get("cuenta")} (@${q.get("usuario")})` });
    } else if (q.get("threads") === "error") {
      setEstado({ ok: false, texto: q.get("msg") || "No se pudo conectar" });
    }
  }, []);

  async function guardarApp() {
    setOcupado(true);
    setEstado(null);
    try {
      await api.post("/api/v1/multiplataforma/meta/threads/app", { app_id: appId.trim(), app_secret: secreto.trim() });
      setSecreto("");
      setEstado({ ok: true, texto: "App de Threads guardada" });
      await cargar();
    } catch (e) {
      setEstado({ ok: false, texto: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setOcupado(false);
    }
  }

  async function conectar() {
    setOcupado(true);
    setEstado(null);
    try {
      const r = await api.get<{ url: string }>("/api/v1/multiplataforma/meta/threads/autorizar");
      window.location.href = r.url;
    } catch (e) {
      setEstado({ ok: false, texto: e instanceof ApiError ? e.message : String(e) });
      setOcupado(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base sm:text-lg">Threads · Conectar con un botón</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground sm:text-sm">
          Entra en threads.com con la cuenta que quieras conectar, vuelve aquí y pulsa «Conectar Threads». Repite
          con cada cuenta. El token se renueva solo.
        </p>
        {app?.url_retorno && (
          <p className="break-all text-xs text-muted-foreground">
            URL de retorno (ponla en la app de Threads): <span className="font-mono">{app.url_retorno}</span>
          </p>
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Input value={appId} onChange={(e) => setAppId(e.target.value)} placeholder="Identificador de la app de Threads" inputMode="numeric" />
          <Input
            value={secreto}
            onChange={(e) => setSecreto(e.target.value)}
            placeholder={app?.configurada ? "Clave secreta guardada (pega otra para cambiarla)" : "Clave secreta de la app de Threads"}
            type="password"
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button variant="outline" onClick={guardarApp} disabled={!appId.trim() || !secreto.trim() || ocupado} className="w-full sm:w-auto">
            Guardar app
          </Button>
          <Button onClick={conectar} disabled={!app?.configurada || ocupado} className="w-full sm:w-auto">
            {ocupado ? "Abriendo…" : "Conectar Threads"}
          </Button>
        </div>
        {estado && (
          <p className={`break-words text-xs sm:text-sm ${estado.ok ? "text-emerald-600" : "text-red-600"}`}>
            {estado.texto}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function ConectarMetaPage() {
  return (
    <div className="container mx-auto max-w-2xl space-y-6 p-4 sm:p-6 md:p-10">
      <header>
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">🔌 Conectar Meta</h1>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Pega los tokens aquí y no en un chat. No se vuelven a enseñar.
        </p>
      </header>
      <Bloque
        titulo="Facebook + Instagram"
        ayuda="Token de usuario ampliado (depurador de tokens › Ampliar token de acceso). Conecta todas las páginas de una vez."
        ruta="/api/v1/multiplataforma/meta/conectar-facebook"
      />
      <ThreadsOAuth />
      <Bloque
        titulo="Threads (pegar token)"
        ayuda="Un token por cuenta (Casos de uso › Threads › Generador de tokens). Pega uno, conecta, y repite con el siguiente."
        ruta="/api/v1/multiplataforma/meta/conectar-threads"
      />
    </div>
  );
}
