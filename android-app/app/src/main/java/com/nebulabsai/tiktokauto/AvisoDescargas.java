package com.nebulabsai.tiktokauto;

import android.app.DownloadManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.IntentFilter;
import android.os.Build;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.drawable.Icon;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.RemoteViews;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * UNA notificación para toda la tanda, con progreso.
 *
 * El gestor de descargas de Android crea una notificación POR FICHERO: bajar
 * diez vídeos llenaba la barra de diez avisos idénticos y no decías por dónde
 * ibas. Aquí se apagan las suyas y se publica una sola: "Bajando 3 de 10", con
 * su barra, y al acabar "10 vídeos listos" que al tocarla abre la carpeta.
 *
 * El progreso se saca preguntándole al gestor cada poco cuántos bytes lleva de
 * cada descarga viva: no avisa por su cuenta mientras baja, solo cuando
 * termina.
 *
 * El aspecto es el de la WEB y no el del sistema: tarjeta oscura, el logo de
 * NebulabsAI y la barra con el degradado cian → violeta de la marca
 * (`res/layout/aviso_descargas.xml`). Va con `DecoratedCustomViewStyle`, que
 * es lo que deja meter un diseño propio conservando la cabecera de Android —
 * una notificación totalmente a medida se ve distinta en cada versión y acaba
 * peor que la del sistema.
 */
class AvisoDescargas {

    private static final String CANAL = "descargas";
    private static final int ID_AVISO = 1001;
    private static final long CADA_MS = 700;

    private final Context ctx;
    private final NotificationManager avisos;
    private final DownloadManager gestor;
    private final Handler reloj = new Handler(Looper.getMainLooper());

    /** Descargas del gestor que siguen vivas: id → nombre. */
    private final Map<Long, String> enMarcha = new LinkedHashMap<>();
    /** Cuántas se han lanzado y cuántas han acabado en ESTA tanda. */
    private int lanzadas = 0;
    private int terminadas = 0;
    private String ultimoNombre = "";
    private boolean mirando = false;
    /** Cuándo se dio de alta la última descarga, para saber dónde acaba una
     *  tanda. */
    private long ultimaAlta = 0;
    /** Si está esperando a la red en vez de bajando, para decirlo en vez de
     *  dejar la barra congelada. */
    private boolean esperando = false;
    /** Qué dice la pausa: "Esperando red", "El servidor falla, reintentando"…
     *  Antes todo STATUS_PAUSED salía como "Esperando red", también cuando era
     *  el servidor (5xx, enlace caducado) y la red estaba bien. */
    private String motivoPausa = "";
    /** Desde cuándo está en pausa cada descarga (id → elapsedRealtime). */
    private final Map<Long, Long> pausadaDesde = new java.util.HashMap<>();
    /** Las que se dieron por perdidas (tope en pausa o «Cancelar»). */
    private int fallidas = 0;
    /** Néstor la quitó: no se vuelve a publicar hasta que haya un cambio de
     *  verdad (otro fichero terminado o cancelado). Antes se republicaba cada
     *  700 ms y era imposible quitarla (5/11/2026). */
    private boolean quitada = false;
    private int terminadasAlQuitar = 0;
    /** Lo último publicado, para no re-notificar si no ha cambiado nada. */
    private String ultimoPintado = "";

    /** Una descarga que lleva más de esto en pausa se cancela y se avisa:
     *  quedarse para siempre en "esperando" no ayuda a nadie. */
    private static final long TOPE_PAUSA_MS = 10 * 60_000;
    private static final String ACCION_CANCELAR = "com.nebulabsai.tiktokauto.CANCELAR_DESCARGAS";
    private static final String ACCION_QUITADA = "com.nebulabsai.tiktokauto.AVISO_QUITADO";

    /** Dos descargas separadas por menos de esto son la MISMA tanda.
     *
     *  La tanda se lanza fichero a fichero con una pausa entre medias (varias
     *  a la vez se cancelan solas en el móvil), así que a ratos no queda
     *  ninguna viva EN MEDIO de la tanda. Decidir por "no queda nada vivo"
     *  reiniciaba la cuenta a mitad y salía "9 de 9" con una todavía bajando.
     *  Por tiempo no se confunde: entre tanda y tanda pasan minutos. */
    private static final long VENTANA_TANDA_MS = 20_000;

    AvisoDescargas(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        this.avisos = (NotificationManager)
            this.ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        this.gestor = (DownloadManager)
            this.ctx.getSystemService(Context.DOWNLOAD_SERVICE);
        NotificationChannel canal = new NotificationChannel(
            CANAL, "Descargas", NotificationManager.IMPORTANCE_LOW);
        canal.setDescription("Vídeos y fotos que se están bajando");
        avisos.createNotificationChannel(canal);

        BroadcastReceiver botones = new BroadcastReceiver() {
            @Override public void onReceive(Context c, Intent i) {
                if (ACCION_CANCELAR.equals(i.getAction())) cancelarTodo();
                else if (ACCION_QUITADA.equals(i.getAction())) quitadaPorUsuario();
            }
        };
        IntentFilter f = new IntentFilter();
        f.addAction(ACCION_CANCELAR);
        f.addAction(ACCION_QUITADA);
        if (Build.VERSION.SDK_INT >= 33) {
            this.ctx.registerReceiver(botones, f, Context.RECEIVER_NOT_EXPORTED);
        } else {
            this.ctx.registerReceiver(botones, f);
        }
    }

    /** Botón «Cancelar»: borra del gestor lo que quede y cierra la tanda. */
    private synchronized void cancelarTodo() {
        // Cada MainActivity crea su AvisoDescargas y todas oyen el botón: la
        // que no lleva ninguna tanda no pinta nada (sacaría "Bajando 0").
        if (lanzadas <= 0) return;
        if (!enMarcha.isEmpty()) {
            long[] ids = new long[enMarcha.size()];
            int i = 0;
            for (Long id : enMarcha.keySet()) ids[i++] = id;
            try { gestor.remove(ids); } catch (Exception ignorada) { }
            fallidas += enMarcha.size();
            terminadas += enMarcha.size();
            enMarcha.clear();
            pausadaDesde.clear();
        }
        // Las de la app (blob:) no se pueden parar desde aquí; se cierran en la cuenta.
        if (terminadas < lanzadas) { fallidas += lanzadas - terminadas; terminadas = lanzadas; }
        quitada = false;
        esperando = false;
        pintar();
    }

    private synchronized void quitadaPorUsuario() {
        quitada = true;
        terminadasAlQuitar = terminadas;
        ultimoPintado = "";
    }

    /** Una descarga que lleva el gestor de Android (fichero por URL). */
    synchronized void empezada(long id, String nombre) {
        // `apuntar` ANTES de meterla en la lista: es quien decide si esto
        // empieza una tanda nueva, y lo decide mirando si queda algo vivo. Al
        // revés, la primera de cada tanda ya estaba dentro, la cuenta no se
        // reiniciaba nunca y se iba sumando a la anterior — de ahí el "11 de
        // 17" al bajar una carpeta de 10 (los 10 de antes + los 7 de ahora).
        apuntar(nombre);
        enMarcha.put(id, nombre);
        quitada = false;
        arrancarVigilancia();
    }

    /** Una que se guarda desde la app (las de tanda, que vienen en `blob:`). */
    synchronized void empezadaSinGestor(String nombre) {
        apuntar(nombre);
        pintar();
    }

    synchronized void terminadaSinGestor() {
        terminadas += 1;
        pintar();
    }

    private void apuntar(String nombre) {
        long ahora = android.os.SystemClock.elapsedRealtime();
        // Tanda nueva: no queda nada vivo Y hace rato que no se daba de alta
        // ninguna. Las dos condiciones hacen falta — ver `VENTANA_TANDA_MS`.
        if (enMarcha.isEmpty() && lanzadas == terminadas
            && ahora - ultimaAlta > VENTANA_TANDA_MS) {
            lanzadas = 0;
            terminadas = 0;
            fallidas = 0;
        }
        ultimaAlta = ahora;
        lanzadas += 1;
        if (nombre != null && !nombre.isEmpty()) ultimoNombre = nombre;
    }

    private void arrancarVigilancia() {
        if (mirando) return;
        mirando = true;
        reloj.postDelayed(this::mirar, CADA_MS);
    }

    /** Le pregunta al gestor cuánto lleva de lo que sigue vivo.
     *
     *  El progreso que se pinta es GLOBAL —ficheros terminados más el trozo
     *  que lleve el que está en marcha— y no la suma de bytes de todos. El
     *  motivo: de los que aún no ha empezado, Android no sabe el tamaño
     *  (`COLUMN_TOTAL_SIZE_BYTES` es -1 hasta que contesta el servidor), así
     *  que sumando bytes no había total fiable y la cifra no aparecía hasta el
     *  final, cuando ya quedaban pocos. Contando ficheros siempre se sabe.
     */
    private synchronized void mirar() {
        // Del que está bajando AHORA, para poder decir por dónde va ese.
        long bytesActivo = 0;
        long totalActivo = 0;
        String nombreActivo = "";
        // Cuánto llevan, en fracción, los que están vivos: es lo que hace que
        // la barra avance entre fichero y fichero.
        double fraccion = 0;

        DownloadManager.Query q = new DownloadManager.Query();
        long[] ids = new long[enMarcha.size()];
        int i = 0;
        for (Long id : enMarcha.keySet()) ids[i++] = id;
        q.setFilterById(ids);

        // Las que el gestor ya no conoce (borradas de su lista, canceladas a
        // mano) no volverían a aparecer NUNCA, y sin esto se quedaban vivas
        // para siempre: la notificación se congelaba en "bajando 1 archivo".
        java.util.Set<Long> vistas = new java.util.HashSet<>();
        boolean algunaEsperando = false;
        String motivo = "";
        boolean preguntaOk = false;
        long ahora = android.os.SystemClock.elapsedRealtime();

        try (Cursor c = gestor.query(q)) {
            while (c != null && c.moveToNext()) {
                long id = c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_ID));
                vistas.add(id);
                int estado = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                // Parada esperando red o esperando a reintentar. Se queda viva
                // y sin avanzar, que es lo que parece "trabado".
                if (estado == DownloadManager.STATUS_PAUSED) {
                    algunaEsperando = true;
                    int razon = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON));
                    String m;
                    switch (razon) {
                        case DownloadManager.PAUSED_WAITING_FOR_NETWORK: m = "Esperando red"; break;
                        case DownloadManager.PAUSED_QUEUED_FOR_WIFI: m = "Esperando wifi"; break;
                        case DownloadManager.PAUSED_WAITING_TO_RETRY: m = "El servidor no responde, reintentando"; break;
                        default: m = "En pausa";
                    }
                    if (motivo.isEmpty()) motivo = m;
                    Long desde = pausadaDesde.get(id);
                    if (desde == null) {
                        pausadaDesde.put(id, ahora);
                    } else if (ahora - desde > TOPE_PAUSA_MS) {
                        // Demasiado tiempo parada: se cancela y se cuenta como fallida.
                        try { gestor.remove(id); } catch (Exception ignorada) { }
                        enMarcha.remove(id);
                        pausadaDesde.remove(id);
                        terminadas += 1;
                        fallidas += 1;
                        continue;
                    }
                } else {
                    pausadaDesde.remove(id);
                }
                long lleva = c.getLong(
                    c.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                long mide = c.getLong(
                    c.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                if (estado == DownloadManager.STATUS_SUCCESSFUL
                    || estado == DownloadManager.STATUS_FAILED) {
                    enMarcha.remove(id);
                    pausadaDesde.remove(id);
                    terminadas += 1;
                    if (estado == DownloadManager.STATUS_FAILED) fallidas += 1;
                    continue;
                }
                if (mide > 0) {
                    fraccion += Math.min(1.0, Math.max(0, lleva) / (double) mide);
                    // El "activo" es el que más lleva bajado: con varios a la
                    // vez, es el que de verdad se está moviendo.
                    if (lleva > bytesActivo) {
                        bytesActivo = lleva;
                        totalActivo = mide;
                        nombreActivo = enMarcha.get(id);
                    }
                }
            }
            preguntaOk = true;
        } catch (Exception ignorada) {
            // Preguntar por el progreso no puede tumbar nada.
        }

        // SOLO si la consulta fue bien: si falló, `vistas` está vacío y esto
        // daría por terminada toda la tanda de golpe.
        if (preguntaOk) {
            java.util.Iterator<Long> it = enMarcha.keySet().iterator();
            while (it.hasNext()) {
                Long sig = it.next();
                if (!vistas.contains(sig)) {
                    it.remove();
                    pausadaDesde.remove(sig);
                    terminadas += 1;
                }
            }
        }
        esperando = algunaEsperando;
        motivoPausa = motivo;

        pintar(bytesActivo, totalActivo, nombreActivo, fraccion);

        if (!enMarcha.isEmpty()) {
            reloj.postDelayed(this::mirar, CADA_MS);
        } else {
            mirando = false;
        }
    }

    private void pintar() {
        pintar(0, 0, "", 0);
    }

    private void pintar(long bytesActivo, long totalActivo, String nombreActivo,
                        double fraccionViva) {
        boolean acabado = enMarcha.isEmpty() && terminadas >= lanzadas && lanzadas > 0;

        String titulo;
        String detalle;
        if (acabado) {
            int bien = Math.max(0, lanzadas - fallidas);
            titulo = (bien == 1 ? "1 archivo listo" : bien + " archivos listos");
            detalle = fallidas > 0
                ? (fallidas == 1 ? "1 no se pudo bajar" : fallidas + " no se pudieron bajar")
                    + " · vuelve a bajarlos desde la web"
                : (lanzadas == 1 ? ultimoNombre : "Toca para abrir la carpeta");
        } else {
            int quedan = Math.max(0, lanzadas - terminadas);
            titulo = quedan == 1 ? "Bajando 1 archivo" : "Bajando " + quedan + " archivos";
            String cual = (nombreActivo == null || nombreActivo.isEmpty())
                ? ultimoNombre : nombreActivo;
            detalle = (lanzadas > 1 ? Math.min(terminadas + 1, lanzadas) + " de " + lanzadas + " · " : "")
                + cual;
            // Decirlo cambia mucho: una barra parada parece la app colgada,
            // y "esperando red" es algo que se puede arreglar.
            if (esperando) {
                titulo = (motivoPausa.isEmpty() ? "En pausa" : motivoPausa) + " · " + titulo.toLowerCase();
            }
        }

        RemoteViews vista = new RemoteViews(ctx.getPackageName(), R.layout.aviso_descargas);
        vista.setTextViewText(R.id.titulo, titulo);
        vista.setTextViewText(R.id.detalle, detalle);
        if (acabado) {
            vista.setViewVisibility(R.id.barra, View.GONE);
            vista.setViewVisibility(R.id.cifras, View.GONE);
        } else {
            vista.setViewVisibility(R.id.barra, View.VISIBLE);
            // Barra GLOBAL: lo ya terminado más lo que lleve el de ahora. Se
            // sabe siempre, así que avanza desde el primer momento.
            int pctGlobal = lanzadas <= 0 ? 0
                : (int) Math.min(100, Math.round((terminadas + fraccionViva) * 100.0 / lanzadas));
            vista.setProgressBar(R.id.barra, 100, pctGlobal, false);

            // Y la cifra, del fichero que está bajando AHORA: es lo que dice si
            // ese en concreto va o se ha quedado parado. Hasta que el servidor
            // no contesta no se sabe su tamaño, y entonces se enseña el global.
            vista.setViewVisibility(R.id.cifras, View.VISIBLE);
            if (totalActivo > 0) {
                int pctActivo = (int) Math.min(100, bytesActivo * 100 / totalActivo);
                vista.setTextViewText(R.id.cifras,
                    "este " + pctActivo + "%  ·  " + megas(bytesActivo)
                        + " de " + megas(totalActivo) + "   ·   total " + pctGlobal + "%");
            } else {
                vista.setTextViewText(R.id.cifras, "total " + pctGlobal + "%");
            }
        }

        // Si la quitó, no se vuelve a sacar hasta que haya un cambio de verdad
        // (otro fichero terminado o la tanda acabada).
        if (quitada && !acabado && terminadas == terminadasAlQuitar) return;
        if (quitada && (acabado || terminadas != terminadasAlQuitar)) quitada = false;
        // Lo mismo que ya está publicado no se vuelve a publicar.
        // Mientras está en pausa la barra no se mueve: re-publicar cada 700 ms
        // lo mismo solo hacía que reapareciera. Bajando sí, que avanza.
        String huella = titulo + "|" + detalle + "|" + acabado;
        if (esperando && huella.equals(ultimoPintado)) return;
        ultimoPintado = huella;

        Notification.Builder n = new Notification.Builder(ctx, CANAL)
            .setSmallIcon(R.drawable.ic_descarga)
            // Tiñe el icono y la cabecera con el cian de la marca.
            .setColor(0xFF15DBF9)
            .setColorized(true)
            .setStyle(new Notification.DecoratedCustomViewStyle())
            .setCustomContentView(vista)
            .setOnlyAlertOnce(true)
            .setContentIntent(abrirDescargas())
            .setDeleteIntent(difusion(ACCION_QUITADA, 2))
            .setAutoCancel(acabado)
            .setOngoing(!acabado);
        if (!acabado) {
            n.addAction(new Notification.Action.Builder(
                Icon.createWithResource(ctx, R.drawable.ic_descarga),
                "Cancelar", difusion(ACCION_CANCELAR, 1)).build());
        }
        if (acabado) {
            // Al terminar, un botón para ir a los ficheros sin buscarlos.
            n.addAction(new Notification.Action.Builder(
                Icon.createWithResource(ctx, R.drawable.ic_descarga),
                "Abrir carpeta", abrirDescargas()).build());
        }

        avisos.notify(ID_AVISO, n.build());
    }

    private static String megas(long bytes) {
        double mb = bytes / 1024d / 1024d;
        return (mb >= 10 ? String.valueOf(Math.round(mb)) : String.format("%.1f", mb)) + " MB";
    }

    private PendingIntent difusion(String accion, int codigo) {
        Intent i = new Intent(accion).setPackage(ctx.getPackageName());
        return PendingIntent.getBroadcast(
            ctx, codigo, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    /** Al tocar la notificación se abre la lista de descargas del móvil. */
    private PendingIntent abrirDescargas() {
        Intent i = new Intent(DownloadManager.ACTION_VIEW_DOWNLOADS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return PendingIntent.getActivity(
            ctx, 0, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
