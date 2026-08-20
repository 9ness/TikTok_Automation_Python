package ai.nebulabs.tiktok.prueba;

import android.app.DownloadManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
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
        enMarcha.put(id, nombre);
        apuntar(nombre);
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

    /** Le pregunta al gestor cuánto lleva de lo que sigue vivo. */
    private synchronized void mirar() {
        long hechos = 0;
        long total = 0;
        boolean algunoSinTamano = false;

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
                hechos += Math.max(0, lleva);
                if (mide > 0) total += mide; else algunoSinTamano = true;
            }
        } catch (Exception ignorada) {
            // Preguntar por el progreso no puede tumbar nada.
        }

        pintar(hechos, total, algunoSinTamano);

        if (!enMarcha.isEmpty()) {
            reloj.postDelayed(this::mirar, CADA_MS);
        } else {
            mirando = false;
        }
    }

    private void pintar() {
        pintar(0, 0, true);
    }

    private void pintar(long hechos, long total, boolean indeterminado) {
        boolean acabado = enMarcha.isEmpty() && terminadas >= lanzadas && lanzadas > 0;

        String titulo;
        String detalle;
        if (acabado) {
            titulo = (lanzadas == 1 ? "1 archivo listo" : lanzadas + " archivos listos");
            detalle = lanzadas == 1 ? ultimoNombre : "Toca para abrir la carpeta";
        } else {
            int quedan = Math.max(0, lanzadas - terminadas);
            titulo = quedan == 1 ? "Bajando 1 archivo" : "Bajando " + quedan + " archivos";
            detalle = (lanzadas > 1 ? (terminadas + 1) + " de " + lanzadas + " · " : "")
                + ultimoNombre;
        }

        RemoteViews vista = new RemoteViews(ctx.getPackageName(), R.layout.aviso_descargas);
        vista.setTextViewText(R.id.titulo, titulo);
        vista.setTextViewText(R.id.detalle, detalle);
        if (acabado) {
            vista.setViewVisibility(R.id.barra, View.GONE);
        } else {
            vista.setViewVisibility(R.id.barra, View.VISIBLE);
            boolean conocido = total > 0 && !indeterminado;
            vista.setProgressBar(
                R.id.barra, 100,
                conocido ? (int) Math.min(100, hechos * 100 / total) : 0,
                !conocido);
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

        avisos.notify(ID_AVISO, n.build());
    }

    /** Al tocar la notificación se abre la lista de descargas del móvil. */
    private PendingIntent abrirDescargas() {
        Intent i = new Intent(DownloadManager.ACTION_VIEW_DOWNLOADS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return PendingIntent.getActivity(
            ctx, 0, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
