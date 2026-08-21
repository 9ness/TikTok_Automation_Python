package com.nebulabsai.tiktokauto;

import android.app.DownloadManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
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
        // Tanda nueva: si no quedaba nada vivo, se reinicia la cuenta.
        if (enMarcha.isEmpty() && lanzadas == terminadas) {
            lanzadas = 0;
            terminadas = 0;
        }
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

        try (Cursor c = gestor.query(q)) {
            while (c != null && c.moveToNext()) {
                long id = c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_ID));
                int estado = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                long lleva = c.getLong(
                    c.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                long mide = c.getLong(
                    c.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                if (estado == DownloadManager.STATUS_SUCCESSFUL
                    || estado == DownloadManager.STATUS_FAILED) {
                    enMarcha.remove(id);
                    terminadas += 1;
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
        } catch (Exception ignorada) {
            // Preguntar por el progreso no puede tumbar nada.
        }

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
            titulo = (lanzadas == 1 ? "1 archivo listo" : lanzadas + " archivos listos");
            detalle = lanzadas == 1 ? ultimoNombre : "Toca para abrir la carpeta";
        } else {
            int quedan = Math.max(0, lanzadas - terminadas);
            titulo = quedan == 1 ? "Bajando 1 archivo" : "Bajando " + quedan + " archivos";
            String cual = (nombreActivo == null || nombreActivo.isEmpty())
                ? ultimoNombre : nombreActivo;
            detalle = (lanzadas > 1 ? (terminadas + 1) + " de " + lanzadas + " · " : "")
                + cual;
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

        Notification.Builder n = new Notification.Builder(ctx, CANAL)
            .setSmallIcon(R.drawable.ic_descarga)
            // Tiñe el icono y la cabecera con el cian de la marca.
            .setColor(0xFF15DBF9)
            .setColorized(true)
            .setStyle(new Notification.DecoratedCustomViewStyle())
            .setCustomContentView(vista)
            .setOnlyAlertOnce(true)
            .setContentIntent(abrirDescargas())
            .setAutoCancel(acabado)
            .setOngoing(!acabado);
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

    /** Al tocar la notificación se abre la lista de descargas del móvil. */
    private PendingIntent abrirDescargas() {
        Intent i = new Intent(DownloadManager.ACTION_VIEW_DOWNLOADS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return PendingIntent.getActivity(
            ctx, 0, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
