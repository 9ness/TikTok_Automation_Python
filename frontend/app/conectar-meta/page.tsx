"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      <Bloque
        titulo="Threads"
        ayuda="Un token por cuenta (Casos de uso › Threads › Generador de tokens). Pega uno, conecta, y repite con el siguiente."
        ruta="/api/v1/multiplataforma/meta/conectar-threads"
      />
    </div>
  );
}
